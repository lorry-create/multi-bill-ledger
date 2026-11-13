"""导入去重与重复文件/相似截图检测服务。

两层防护共用本模块：
1. 批次级原件检测：对上传文件计算加密域 HMAC 指纹（file_digest）与视觉结构指纹（visual_fp），
   在同用户的历史未失败/有效批次中检出完全相同文件（exact_file）或高度相似截图（similar_image），
   并在扫描旧批次时懒回填缺失指纹（兼容既有的 local-data/app.db，零 DDL 变更）。
2. 交易级容错判重：除精确 dedupe_digest 命中 duplicate 外，针对未提供源单号（如列表截图）
   与导出账单（CSV/XLSX）跨形式重复或文字微调，按同平台同方向同日同金额+相似商户检出 suspected，
   并返回脱敏可读摘要（时间、商户、金额），供导入确认与提交前弹窗预警。
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..contracts import (
    BatchStatus,
    DuplicateBatchMatch,
    FlowType,
    IngestionMethod,
)
from ..crypto import (
    CryptoError,
    decrypt_bytes,
    decrypt_json,
    encrypt_json,
    file_digest,
)
from ..db import as_utc, utcnow
from ..intelligence.normalize import normalize_merchant
from .dedupe import day_key, flow_value, month_index, row_digest

DAY_ZONE = ZoneInfo("Asia/Shanghai")

logger = logging.getLogger("app.duplicate_detector")

ISSUE_DUPLICATE_FILE = "DUPLICATE_FILE_UPLOADED"
ISSUE_SIMILAR_IMAGE = "SIMILAR_IMAGE_UPLOADED"

_PLACEHOLDER_MERCHANTS = {"", "未知商户", "未知", "商家", "商户"}
_SCAN_BATCH_LIMIT = 60
_MIN_VISUAL_SIDE = 32
_MIN_VISUAL_ENERGY = 30.0
_MIN_BAND_COSINE = 0.88
_AVG_BAND_COSINE = 0.92


class DuplicateRowProbe(NamedTuple):
    """单行判重探测输入（兼容草稿与编辑后前端提交行）。"""

    row_id: str
    source_transaction_id: str | None
    occurred_at: datetime | None
    amount_fen: int | None
    flow_type: FlowType | str | None
    merchant: str
    description: str


class DuplicateEval(NamedTuple):
    """单行判重结论与向用户展示的命中摘要。"""

    duplicate_status: str  # "unique" | "duplicate" | "suspected"
    reason: str
    matched_summary: str


def compute_image_fingerprint(data: bytes) -> dict[str, Any] | None:
    """提取对状态栏时间、轻度压缩/缩放与轻微裁剪鲁棒的高频字形指纹。

    返回紧致结构（约 2400 字符十六进制像素强度网格），只保存在加密列
    encrypted_filename 内；纯色/极小占位图与无法解码内容返回 None，避免误报。
    """
    try:
        with Image.open(io.BytesIO(data)) as raw:
            gray = raw.convert("L")
            width, height = gray.size
            if width < _MIN_VISUAL_SIDE or height < _MIN_VISUAL_SIDE:
                return None
            # 截去常见手机状态栏与底部指示条、左侧泛用商户图标栏，聚焦商户名与金额文字区域
            x0, x1 = int(width * 0.16), int(width * 0.96)
            y0, y1 = int(height * 0.08), int(height * 0.94)
            if x1 - x0 < 8 or y1 - y0 < 8:
                return None
            cropped = gray.crop((x0, y0, x1, y1))
            sampled = cropped.resize((40, 60), Image.Resampling.BOX).filter(
                ImageFilter.BoxBlur(1)
            )
            arr = np.asarray(sampled, dtype=np.float32)
    except Exception:
        return None

    # 减去每行横向中位底色：剥离白底与横跨整卡片的背景/分隔线，只保留暗字或亮字笔画
    row_bg = np.median(arr, axis=1, keepdims=True)
    fg = np.maximum(0.0, np.abs(arr - row_bg) - 1.5)
    if float(np.linalg.norm(fg)) < _MIN_VISUAL_ENERGY:
        return None

    scale = float(np.percentile(fg, 99))
    if scale < 1e-6:
        return None
    quant = np.clip(np.round(fg / scale * 15.0), 0, 15).astype(np.uint8)
    hex_grid = "".join(f"{int(v):x}" for v in quant.ravel())
    return {"v": 1, "w": int(width), "h": int(height), "g": hex_grid}


def _decode_grid(sig: dict[str, Any] | None) -> np.ndarray | None:
    if not isinstance(sig, dict) or sig.get("v") != 1:
        return None
    hex_grid = sig.get("g")
    if not isinstance(hex_grid, str) or len(hex_grid) != 40 * 60:
        return None
    try:
        vals = np.fromiter((int(ch, 16) for ch in hex_grid), dtype=np.float32, count=2400)
    except ValueError:
        return None
    return vals.reshape((60, 40))


def compare_image_fingerprints(
    sig_a: dict[str, Any] | None, sig_b: dict[str, Any] | None
) -> tuple[bool, float]:
    """用三段抗偏移局部余弦相似度判定两张截图是否为同一画面。"""
    if not sig_a or not sig_b:
        return False, 0.0
    wa, ha = sig_a.get("w"), sig_a.get("h")
    wb, hb = sig_b.get("w"), sig_b.get("h")
    if not (isinstance(wa, int) and isinstance(ha, int) and isinstance(wb, int) and isinstance(hb, int)):
        return False, 0.0
    if wa <= 0 or ha <= 0 or wb <= 0 or hb <= 0:
        return False, 0.0
    ra, rb = wa / ha, wb / hb
    if max(ra / rb, rb / ra) > 1.25:
        return False, 0.0

    arr_a = _decode_grid(sig_a)
    arr_b = _decode_grid(sig_b)
    if arr_a is None or arr_b is None:
        return False, 0.0

    rows, cols = arr_a.shape
    band_h = rows // 3
    band_scores: list[float] = []
    for k in range(3):
        a0, a1 = k * band_h, (k + 1) * band_h
        best = 0.0
        for dy in range(-4, 5):
            ya0 = max(a0, 0 - dy)
            ya1 = min(a1, rows - dy)
            if ya1 - ya0 < 12:
                continue
            yb0, yb1 = ya0 + dy, ya1 + dy
            for dx in range(-2, 3):
                x1s, x1e = max(0, dx), cols + min(0, dx)
                x2s, x2e = max(0, -dx), cols + min(0, -dx)
                pa = arr_a[ya0:ya1, x1s:x1e].ravel()
                pb = arr_b[yb0:yb1, x2s:x2e].ravel()
                na = float(np.linalg.norm(pa))
                nb = float(np.linalg.norm(pb))
                if na < 1e-6 and nb < 1e-6:
                    score = 1.0
                elif na < 1e-6 or nb < 1e-6:
                    score = 0.0
                else:
                    score = float(np.dot(pa, pb) / (na * nb))
                if score > best:
                    best = score
        band_scores.append(best)

    min_score = min(band_scores)
    avg_score = sum(band_scores) / len(band_scores)
    matched = min_score >= _MIN_BAND_COSINE and avg_score >= _AVG_BAND_COSINE
    return matched, avg_score


def read_filename_meta(batch: models.ImportBatch, key: str) -> dict[str, Any]:
    """安全解密 encrypted_filename JSON（兼容旧结构与带指纹结构）。"""
    try:
        payload = decrypt_json(key, batch.encrypted_filename or "")
        if not isinstance(payload, dict):
            payload = {}
    except CryptoError:
        payload = {}
    dup_raw = payload.get("duplicate_match")
    return {
        "name": str(payload.get("name") or "未知文件"),
        "media_type": str(payload.get("media_type") or "application/octet-stream"),
        "file_digest": payload.get("file_digest"),
        "visual_fp": payload.get("visual_fp"),
        "duplicate_match": dup_raw if isinstance(dup_raw, dict) else None,
        "_raw": payload,
    }


def batch_created_count(batch: models.ImportBatch, key: str) -> int:
    """读取历史批次实际已确认入账的交易数（未完成返回 0）。"""
    if batch.status != BatchStatus.completed.value or not batch.encrypted_confirm_result:
        return 0
    try:
        payload = decrypt_json(key, batch.encrypted_confirm_result)
        return max(0, int(payload.get("created_count", 0)))
    except (CryptoError, TypeError, ValueError):
        return 0


def build_duplicate_match(
    batch: models.ImportBatch, meta: dict[str, Any], key: str, match_type: str
) -> DuplicateBatchMatch:
    return DuplicateBatchMatch(
        batch_id=batch.id,
        file_name=str(meta.get("name") or "未知文件"),
        created_at=as_utc(batch.created_at),
        status=BatchStatus(batch.status),
        created_count=batch_created_count(batch, key),
        match_type=match_type,  # type: ignore[arg-type]
    )


def refresh_duplicate_match(
    db: Session, match: DuplicateBatchMatch | None, key: str
) -> DuplicateBatchMatch | None:
    """读取最新历史批次状态与已入账笔数（例如原草稿批次刚刚被确认入账）。"""
    if match is None:
        return None
    target = db.get(models.ImportBatch, match.batch_id)
    if target is None:
        return match
    return match.model_copy(
        update={
            "status": BatchStatus(target.status),
            "created_count": batch_created_count(target, key),
        }
    )


def _ensure_candidate_fingerprints(
    candidate: models.ImportBatch, meta: dict[str, Any], key: str
) -> bool:
    """懒回填 Scheme B 上线前存量批次的 file_digest / visual_fp，避免需要迁移脚本。"""
    need_digest = not isinstance(meta.get("file_digest"), str)
    is_shot = candidate.ingestion_method == IngestionMethod.screenshot.value
    need_visual = is_shot and "visual_fp" not in meta.get("_raw", {})
    if not need_digest and not need_visual:
        return False
    if not candidate.encrypted_original:
        return False
    try:
        raw = decrypt_bytes(key, candidate.encrypted_original)
    except CryptoError:
        return False

    raw_meta = dict(meta.get("_raw") or {})
    raw_meta.setdefault("name", meta["name"])
    raw_meta.setdefault("media_type", meta["media_type"])
    if need_digest:
        meta["file_digest"] = file_digest(key, raw)
        raw_meta["file_digest"] = meta["file_digest"]
    if need_visual:
        vfp = compute_image_fingerprint(raw)
        meta["visual_fp"] = vfp
        raw_meta["visual_fp"] = vfp
    candidate.encrypted_filename = encrypt_json(key, raw_meta)
    return True


def find_matching_prior_batch(
    db: Session,
    *,
    user_id: str,
    method: IngestionMethod,
    fdigest: str,
    visual_fp: dict[str, Any] | None,
    key: str,
    exclude_batch_id: str | None = None,
) -> DuplicateBatchMatch | None:
    """在当前用户的有效历史导入批次中检测相同文件或高度相似截图。"""
    now = utcnow()
    rows = list(
        db.scalars(
            select(models.ImportBatch)
            .where(
                models.ImportBatch.user_id == user_id,
                models.ImportBatch.status != BatchStatus.failed.value,
            )
            .order_by(models.ImportBatch.created_at.desc())
            .limit(_SCAN_BATCH_LIMIT)
        )
    )

    best_similar: tuple[int, float, models.ImportBatch, dict[str, Any]] | None = None
    dirty = False

    for cand in rows:
        if exclude_batch_id and cand.id == exclude_batch_id:
            continue
        if cand.status != BatchStatus.completed.value and as_utc(cand.expires_at) < now:
            continue

        meta = read_filename_meta(cand, key)
        if _ensure_candidate_fingerprints(cand, meta, key):
            dirty = True

        if meta.get("file_digest") == fdigest:
            if dirty:
                db.flush()
            return build_duplicate_match(cand, meta, key, "exact_file")

        if (
            method is IngestionMethod.screenshot
            and visual_fp is not None
            and cand.ingestion_method == IngestionMethod.screenshot.value
        ):
            matched, score = compare_image_fingerprints(visual_fp, meta.get("visual_fp"))
            if matched:
                # 优先提示已确认入账的批次；同优先度下取画面最像的
                priority = 1 if cand.status == BatchStatus.completed.value else 0
                if best_similar is None or (priority, score) > (best_similar[0], best_similar[1]):
                    best_similar = (priority, score, cand, meta)

    if dirty:
        db.flush()
    if best_similar is not None:
        _, _, hit, meta = best_similar
        return build_duplicate_match(hit, meta, key, "similar_image")
    return None


def _merchant_token(raw: str) -> str:
    norm = normalize_merchant(raw or "")
    cleaned = re.sub(r"[\W_]+", "", norm.lower())
    return cleaned


def _merchants_compatible(
    left: str, right: str, t_left: datetime, t_right: datetime
) -> bool:
    tl = _merchant_token(left)
    tr = _merchant_token(right)
    if tl and tr:
        if tl == tr:
            return True
        shorter, longer = (tl, tr) if len(tl) <= len(tr) else (tr, tl)
        if len(shorter) >= 2 and shorter in longer:
            return True
        return False

    # 截图某一方缺失商户名称（如"未知商户"）时，要求双方交易时间精确到 ±2 分钟内再关联
    left_placeholder = (left or "").strip() in _PLACEHOLDER_MERCHANTS or not tl
    right_placeholder = (right or "").strip() in _PLACEHOLDER_MERCHANTS or not tr
    if (left_placeholder or right_placeholder) and abs((t_left - t_right).total_seconds()) <= 120:
        return True
    return False


def _format_summary(payload: dict[str, Any]) -> str:
    occ_raw = str(payload.get("occurred_at") or "")
    when = occ_raw
    try:
        dt = datetime.fromisoformat(occ_raw)
        when = as_utc(dt).astimezone(DAY_ZONE).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    merchant = str(payload.get("merchant") or "未知商户").strip() or "未知商户"
    try:
        fen = int(payload.get("amount_fen") or 0)
        amt = f"¥{fen / 100:.2f}"
    except (TypeError, ValueError):
        amt = ""
    return f"{when} {merchant} {amt}".strip()


def evaluate_rows_duplicates(
    db: Session,
    *,
    user_id: str,
    source: str,
    rows: list[DuplicateRowProbe],
    key: str,
) -> dict[str, DuplicateEval]:
    """统一判重：先查精确 dedupe_digest，再按同日同金额+商户容错查疑似跨形式重复。"""
    results: dict[str, DuplicateEval] = {}
    need_months: set[str] = set()
    prepared: list[tuple[DuplicateRowProbe, str]] = []

    for row in rows:
        if row.occurred_at is None or row.amount_fen is None or row.flow_type is None:
            results[row.row_id] = DuplicateEval("unique", "", "")
            continue
        ft = row.flow_type if isinstance(row.flow_type, FlowType) else FlowType(str(row.flow_type))
        dig = row_digest(
            key,
            source=source,
            flow_type=ft,
            source_transaction_id=row.source_transaction_id,
            occurred_at=row.occurred_at,
            amount_fen=row.amount_fen,
            merchant=row.merchant,
            description=row.description,
        )
        hit = db.scalar(
            select(models.Transaction).where(
                models.Transaction.user_id == user_id,
                models.Transaction.dedupe_digest == dig,
            )
        )
        if hit is not None:
            summary = ""
            try:
                summary = _format_summary(decrypt_json(key, hit.encrypted_payload))
            except CryptoError:
                summary = ""
            results[row.row_id] = DuplicateEval(
                "duplicate",
                "与已入账记录精确匹配（同平台同时间同金额/单号）",
                summary,
            )
            continue

        need_months.add(month_index(row.occurred_at))
        prepared.append((row, dig))

    if not prepared:
        return results

    # 批量按 (user_id, source, month_index) 拉取一次，避免 N 行逐次全表解密
    candidates_by_bucket: dict[tuple[str, str], list[dict[str, Any]]] = {}
    records = list(
        db.scalars(
            select(models.Transaction).where(
                models.Transaction.user_id == user_id,
                models.Transaction.source == source,
                models.Transaction.month_index.in_(list(need_months)),
            )
        )
    )
    for rec in records:
        try:
            payload = decrypt_json(key, rec.encrypted_payload)
        except CryptoError:
            continue
        if not isinstance(payload, dict):
            continue
        occ_raw = payload.get("occurred_at")
        if not isinstance(occ_raw, str):
            continue
        try:
            occ_dt = datetime.fromisoformat(occ_raw)
        except ValueError:
            continue
        if occ_dt.tzinfo is None:
            continue
        payload["_parsed_dt"] = occ_dt
        payload["_day"] = day_key(occ_dt)
        bucket_key = (rec.month_index, rec.flow_type)
        candidates_by_bucket.setdefault(bucket_key, []).append(payload)

    for row, _ in prepared:
        assert row.occurred_at is not None and row.amount_fen is not None and row.flow_type is not None
        r_month = month_index(row.occurred_at)
        r_day = day_key(row.occurred_at)
        r_flow = flow_value(row.flow_type)
        r_oid = (row.source_transaction_id or "").strip()

        # 精确到 ±2 分钟时，允许 expense/transfer 这两种微信列表常见标注互判
        flow_candidates = [r_flow]
        if r_flow in {"expense", "transfer"}:
            flow_candidates.append("transfer" if r_flow == "expense" else "expense")

        matched_payload: dict[str, Any] | None = None
        for idx_flow, cand_flow in enumerate(flow_candidates):
            for cand in candidates_by_bucket.get((r_month, cand_flow), ()):
                if cand.get("_day") != r_day:
                    continue
                if int(cand.get("amount_fen") or 0) != int(row.amount_fen):
                    continue
                c_oid = str(cand.get("source_transaction_id") or "").strip()
                # 若双方都有明确且不同的平台交易单号，属于两笔独立订单，不跨单号误判
                if r_oid and c_oid and r_oid != c_oid:
                    continue
                c_dt = cand["_parsed_dt"]
                time_diff = abs((as_utc(row.occurred_at) - as_utc(c_dt)).total_seconds())
                # 若流向不同（expense vs transfer），严格要求时间差 ≤ 120s
                if idx_flow > 0 and time_diff > 120:
                    continue
                if _merchants_compatible(
                    row.merchant, str(cand.get("merchant") or ""), row.occurred_at, c_dt
                ):
                    matched_payload = cand
                    break
            if matched_payload is not None:
                break

        if matched_payload is not None:
            summary = _format_summary(matched_payload)
            results[row.row_id] = DuplicateEval(
                "suspected",
                f"与历史已入账记录疑似重复（同日同金额相近商户：{summary}），请核对是否重复上传",
                summary,
            )
        else:
            results[row.row_id] = DuplicateEval("unique", "", "")

    return results


__all__ = [
    "DuplicateEval",
    "DuplicateRowProbe",
    "ISSUE_DUPLICATE_FILE",
    "ISSUE_SIMILAR_IMAGE",
    "build_duplicate_match",
    "compare_image_fingerprints",
    "compute_image_fingerprint",
    "evaluate_rows_duplicates",
    "find_matching_prior_batch",
    "read_filename_meta",
    "refresh_duplicate_match",
]
