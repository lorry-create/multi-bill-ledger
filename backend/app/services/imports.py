"""导入批次的全部服务端逻辑：收文件、跑解析分类、状态机、确认入账。

为什么集中在一个模块：状态机是本项目最容易写歪的地方（docs/13 列了 5 条容易漏的
细节）。把「谁能改 status」「什么时候 version+1」收在一处，路由层只做 HTTP 适配，
这样加接口或写测试时不会各改一套。

状态机（docs/02）：
    uploaded → processing → pending_review → completed
                    ↓             ↓
                  failed ←────────┘（不，失败只从 uploaded/processing 来）

- `uploaded`：已落库、等 worker 认领。**原子认领**：`UPDATE ... WHERE status='uploaded'`，
  rowcount==1 才算抢到，多进程下不会重复处理同一个批次。
- `processing`：worker 正在解析。超过 `batch_deadline_seconds` 仍未结束由巡检转 failed。
- `pending_review`：草稿可确认。确认成功转 `completed`，一次成功确认，之后新 request_id 一律 409。
- `failed`：整体失败（模板不识别、文件损坏、超时、服务重启中断），可重试。

两条不可妥协的规则：
1. 任何异常路径都必须给批次一个终态，绝不允许永久 `processing`（docs/08 A12）。
2. 金额只以 `encrypted_payload` 形式落库，表上的索引列（月份/类别/流向）是明文，
   这点在 docs/13 已声明泄露范围，不要顺手把商户名也搬到明文列。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import timedelta
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..contracts import (
    Batch,
    BatchStatus,
    ClassificationRule,
    ClassificationSource,
    ConfirmResult,
    ErrorDetails,
    FieldError,
    FlowType,
    IngestionMethod,
    Issue,
    Progress,
    ResolveMissingInput,
    ResolvedCategory,
    Source,
    TransactionDraft,
    TransactionInput,
)
from ..crypto import CryptoError, decrypt_bytes, decrypt_json, encrypt_bytes, encrypt_json
from ..db import as_utc, utcnow
from ..errors import ApiError
from ..intelligence import resolve_missing_deterministic
from ..intelligence.base import (
    ISSUE_DRAFT_UNREADABLE,
    ISSUE_DUPLICATE_EXISTING,
    ISSUE_DUPLICATE_SUSPECTED,
    ISSUE_NO_ROWS_PARSED,
    IntelligenceFailure,
    IntelligenceProvider,
    assert_one_result_per_row,
)
from .dedupe import flow_value, month_index, row_digest

STATUS_UPLOADED = BatchStatus.uploaded.value
STATUS_PROCESSING = BatchStatus.processing.value
STATUS_PENDING_REVIEW = BatchStatus.pending_review.value
STATUS_COMPLETED = BatchStatus.completed.value
STATUS_FAILED = BatchStatus.failed.value

# 批次级失败码（写进 issues，前端按 code 判断该显示哪种失败页）
BATCH_TIMEOUT = "BATCH_TIMEOUT"
BATCH_INTERRUPTED = "BATCH_INTERRUPTED"
BATCH_EXPIRED = "BATCH_EXPIRED"
CRYPTO_FAILED = "CRYPTO_FAILED"

# 只有这四种文件进得来（docs/11 createImport）
_FILE_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

READ_CHUNK = 64 * 1024
_MAX_NAME_LENGTH = 120


class UploadTarget(NamedTuple):
    """校验通过的落库目标：安全文件名、媒体类型、字节上限。"""

    file_name: str
    media_type: str
    max_bytes: int


# ---------------------------------------------------------------- 上传校验


def _unprocessable(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        "VALIDATION_ERROR",
        422,
        message,
        details=ErrorDetails(
            fields=[FieldError(field=field, row_id=None, code=code, message=message)]
        ),
    )


def sanitize_filename(raw: str | None) -> str:
    """只留文件名本身。

    客户端可能传来 `C:\\Users\\me\\Desktop\\账单.csv` 或 `../../etc/passwd`。我们
    不落磁盘、也不拼路径，但文件名会回显给用户，留着路径既难看也泄露本机结构。
    """
    text = (raw or "").replace("\\", "/").strip()
    name = text.rsplit("/", 1)[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable())
    if not name or name in {".", ".."}:
        raise _unprocessable("file", "FILENAME_MISSING", "缺少文件名，请重新选择文件")
    if len(name) > _MAX_NAME_LENGTH:
        stem, suffix = os.path.splitext(name)
        keep = max(1, _MAX_NAME_LENGTH - len(suffix))
        name = stem[:keep] + suffix
    return name


def resolve_target(
    method: IngestionMethod, filename: str | None, settings: Settings
) -> UploadTarget:
    """先定类型再读文件：读之前就要知道字节上限，否则 11MiB 会先被读进内存。"""
    name = sanitize_filename(filename)
    suffix = os.path.splitext(name)[1].lower()

    if method is IngestionMethod.screenshot:
        media_type = _IMAGE_TYPES.get(suffix)
        if media_type is None:
            raise ApiError(
                "UNSUPPORTED_MEDIA_TYPE", 415, "截图只接受 PNG 或 JPEG"
            )
        return UploadTarget(name, media_type, settings.upload_max_image_bytes)

    media_type = _FILE_TYPES.get(suffix)
    if media_type is None:
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE", 415, "只接受支付平台导出的 CSV 或 XLSX 文件"
        )
    return UploadTarget(name, media_type, settings.upload_max_file_bytes)


def _decodable(data: bytes) -> bool:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            data.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def check_content(target: UploadTarget, data: bytes) -> None:
    """校验真实内容，不信客户端声明的类型。

    把 PDF 改名成 .csv 是最常见的手滑。只看扩展名会一路跑到解析层才炸，
    用户看到的是"模板不识别"，其实是他传错了文件——415 才说得清。
    """
    if not data:
        raise _unprocessable("file", "EMPTY_FILE", "文件内容为空，请重新导出后再上传")
    if len(data) > target.max_bytes:
        raise _too_large(target)

    suffix = os.path.splitext(target.file_name)[1].lower()
    if suffix == ".png":
        ok = data[:8] == b"\x89PNG\r\n\x1a\n"
    elif suffix in (".jpg", ".jpeg"):
        ok = data[:3] == b"\xff\xd8\xff"
    elif suffix == ".xlsx":
        # xlsx 是 zip 容器，魔数 PK\x03\x04
        ok = data[:2] == b"PK"
    else:  # csv
        ok = b"\x00" not in data[:8192] and _decodable(data)
    if not ok:
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE",
            415,
            "文件内容与扩展名不符，请上传平台原样导出的文件",
        )


def _too_large(target: UploadTarget) -> ApiError:
    mib = max(1, target.max_bytes // (1024 * 1024))
    return ApiError("UPLOAD_TOO_LARGE", 413, f"文件超过 {mib}MiB")


def read_limited(stream, target: UploadTarget) -> bytes:
    """分块读到上限为止，超了立刻停。

    直接用 `UploadFile.read()` 会把 100MiB 整个吞进内存再判断，等于把 413
    这道防线变成 OOM。
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > target.max_bytes:
            raise _too_large(target)
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------- 批次读写


def create_batch(
    db: Session,
    *,
    user_id: str,
    source: Source,
    method: IngestionMethod,
    target: UploadTarget,
    data: bytes,
    settings: Settings,
) -> models.ImportBatch:
    now = utcnow()
    key = settings.data_encryption_key
    batch = models.ImportBatch(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source=source.value,
        ingestion_method=method.value,
        status=STATUS_UPLOADED,
        version=1,
        progress_current=0,
        progress_total=0,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=settings.batch_draft_ttl_hours),
        encrypted_filename=encrypt_json(
            key, {"name": target.file_name, "media_type": target.media_type}
        ),
        encrypted_original=encrypt_bytes(key, data),
    )
    db.add(batch)
    db.commit()
    return batch


def file_meta(batch: models.ImportBatch, key: str) -> dict[str, str]:
    try:
        payload = decrypt_json(key, batch.encrypted_filename or "")
    except CryptoError:
        payload = {}
    return {
        "name": str(payload.get("name") or "未知文件"),
        "media_type": str(payload.get("media_type") or "application/octet-stream"),
    }


def load_drafts(batch: models.ImportBatch, key: str) -> tuple[list[TransactionDraft], list[Issue]]:
    """解密草稿与问题清单。

    失败批次没有草稿，只有一条失败原因 —— 它存在 `encrypted_issues` 里。
    两处都要读，否则界面上的"失败原因"永远是空的，用户只能看到一个红叉。
    """
    rows: list[TransactionDraft] = []
    issues: list[Issue] = []

    if batch.encrypted_rows:
        try:
            payload = decrypt_json(key, batch.encrypted_rows)
        except CryptoError:
            issues.append(
                Issue(
                    row_id=None,
                    field=None,
                    code=ISSUE_DRAFT_UNREADABLE,
                    message="批次草稿无法解密，请重新上传该账单",
                )
            )
            payload = None
        if payload is not None:
            rows = [
                TransactionDraft.model_validate(item) for item in payload.get("rows", [])
            ]
            issues.extend(
                Issue.model_validate(item) for item in payload.get("issues", [])
            )

    if batch.encrypted_issues:
        try:
            failure = decrypt_json(key, batch.encrypted_issues)
            issues.extend(
                Issue.model_validate(item) for item in failure.get("issues", [])
            )
        except CryptoError:
            issues.append(
                Issue(
                    row_id=None,
                    field=None,
                    code=ISSUE_DRAFT_UNREADABLE,
                    message="批次失败原因无法解密，请重新上传该账单",
                )
            )
    return rows, issues


def load_rules(db: Session, user_id: str, source: str, key: str) -> list[ClassificationRule]:
    """只取**本人 + 本平台 + 启用**的规则。

    在 SQL 里筛平台，而不是交给分类器猜：同一商户名在支付宝和微信是两码事，
    混用会让个人规则串平台生效。
    """
    records = db.scalars(
        select(models.ClassificationRule).where(
            models.ClassificationRule.user_id == user_id,
            models.ClassificationRule.source == source,
            models.ClassificationRule.enabled.is_(True),
        )
    ).all()

    items: list[ClassificationRule] = []
    for record in records:
        try:
            payload = decrypt_json(key, record.encrypted_payload)
            items.append(
                ClassificationRule(
                    id=record.id,
                    version=record.version,
                    source=Source(record.source),
                    merchant_normalized=payload["merchant_normalized"],
                    category=ResolvedCategory(payload["category"]),
                    enabled=record.enabled,
                )
            )
        except (CryptoError, KeyError, ValueError):
            # 单条规则坏了不该让整批分类失败，跳过即可，规则列表接口会暴露异常
            continue
    return items


def to_contract(batch: models.ImportBatch, key: str) -> Batch:
    rows, issues = load_drafts(batch, key)
    meta = file_meta(batch, key)
    return Batch(
        id=batch.id,
        version=batch.version,
        source=Source(batch.source),
        ingestion_method=IngestionMethod(batch.ingestion_method),
        status=BatchStatus(batch.status),
        rows=rows,
        issues=issues,
        progress=Progress(
            current=batch.progress_current,
            total=batch.progress_total or None,
        ),
        file_name=meta["name"],
        created_at=as_utc(batch.created_at),
        updated_at=as_utc(batch.updated_at),
    )


def load_owned(db: Session, user_id: str, batch_id: str) -> models.ImportBatch:
    """别人的批次一律 404，不是 403：403 会泄露"这个 ID 存在"。"""
    batch = db.get(models.ImportBatch, batch_id)
    if batch is None or batch.user_id != user_id:
        raise ApiError("RESOURCE_NOT_FOUND", 404, "资源不存在", details=ErrorDetails())
    return batch


def is_expired(batch: models.ImportBatch) -> bool:
    expires_at = as_utc(batch.expires_at)
    return expires_at is not None and expires_at <= utcnow()


# ---------------------------------------------------------------- 失败与恢复


def mark_failed(
    db: Session,
    batch: models.ImportBatch,
    code: str,
    message: str,
    key: str,
    *,
    commit: bool = True,
) -> None:
    """给批次一个终态。任何失败路径都必须走这里，否则批次会永远停在 processing。"""
    now = utcnow()
    batch.status = STATUS_FAILED
    batch.version += 1
    batch.updated_at = now
    batch.encrypted_rows = None
    batch.progress_current = 0
    batch.encrypted_issues = encrypt_json(
        key,
        {"issues": [Issue(row_id=None, field=None, code=code, message=message).model_dump(mode="json")]},
    )
    if commit:
        db.commit()


# ---------------------------------------------------------------- 处理管线


def _merge_classification(
    draft: TransactionDraft, category, source, reason, extra: list[Issue]
) -> TransactionDraft:
    return draft.model_copy(
        update={
            "category": category,
            "classification_source": source,
            "classification_reason": reason,
            "issues": list(draft.issues) + extra,
        }
    )


def mark_duplicates(
    db: Session,
    *,
    user_id: str,
    source: str,
    drafts: list[TransactionDraft],
    key: str,
    issues: list[Issue],
) -> list[TransactionDraft]:
    """拿每行的摘要去比对已入账交易，撞上的标 duplicate。

    没有这一步，用户重传同一份文件会看到一屏"可入账"的草稿，点确认才被
    静默跳过——那种体验比直接标出来差得多。
    """
    marked: list[TransactionDraft] = []
    for draft in drafts:
        if draft.occurred_at is None or draft.amount_fen is None:
            marked.append(draft)
            continue
        digest = row_digest(
            key,
            source=source,
            flow_type=draft.flow_type or FlowType.expense,
            source_transaction_id=draft.source_transaction_id,
            occurred_at=draft.occurred_at,
            amount_fen=draft.amount_fen,
            merchant=draft.merchant,
            description=draft.description,
        )
        hit = db.scalar(
            select(models.Transaction.id).where(
                models.Transaction.user_id == user_id,
                models.Transaction.dedupe_digest == digest,
            )
        )
        if hit is None:
            marked.append(draft)
            continue
        issue = Issue(
            row_id=draft.row_id,
            field="source_transaction_id",
            code=ISSUE_DUPLICATE_EXISTING,
            message="该交易此前已入账，确认时会自动跳过",
        )
        marked.append(
            draft.model_copy(
                update={
                    "duplicate_status": "duplicate",
                    "issues": list(draft.issues) + [issue],
                }
            )
        )
        issues.append(issue)
    return marked


def process_batch(
    db: Session,
    batch: models.ImportBatch,
    provider: IntelligenceProvider,
    settings: Settings,
) -> None:
    """uploaded/processing 批次的完整处理。worker 认领后调用，内部负责提交。"""
    key = settings.data_encryption_key
    deadline_at = as_utc(batch.created_at) + timedelta(
        seconds=settings.batch_deadline_seconds
    )
    if utcnow() > deadline_at:
        mark_failed(db, batch, BATCH_TIMEOUT, "批次处理超时，请点击重试", key)
        return

    try:
        data = decrypt_bytes(key, batch.encrypted_original or "")
    except CryptoError:
        # 密钥换过或密文损坏。绝不回传内容细节，只说"解不开"
        mark_failed(db, batch, CRYPTO_FAILED, "服务端无法解开该批次的原文件，请重新上传", key)
        return

    meta = file_meta(batch, key)
    try:
        if batch.ingestion_method == IngestionMethod.screenshot.value:
            parsed = provider.recognize_bill_image(data, meta["media_type"], batch.source)
        else:
            parsed = provider.parse_bill_file(data, meta["name"], batch.source)
    except IntelligenceFailure as exc:
        # 整体不可解析才失败；单行坏由 Issue 表达，不能让一条坏行拖垮整份账单
        mark_failed(db, batch, exc.code, exc.message, key)
        return

    issues: list[Issue] = list(parsed.issues)
    drafts: list[TransactionDraft] = list(parsed.rows)

    if drafts:
        rules = load_rules(db, batch.user_id, batch.source, key)
        try:
            use_llm = bool(settings.deepseek_api_key and provider.name != "fallback-rules")
            results = provider.classify_transactions(drafts, rules, use_llm=use_llm)
            assert_one_result_per_row(drafts, results)
        except IntelligenceFailure as exc:
            # docs/13：分类失败可回退 pending 类别，而不是让整批可识别账单全部丢失
            issues.append(
                Issue(row_id=None, field="category", code=exc.code, message=exc.message)
            )
        else:
            by_row = {item.row_id: item for item in results}
            merged: list[TransactionDraft] = []
            for draft in drafts:
                result = by_row[draft.row_id]
                merged.append(
                    _merge_classification(
                        draft,
                        result.category,
                        result.classification_source,
                        result.classification_reason,
                        list(result.issues),
                    )
                )
                issues.extend(result.issues)
            drafts = merged

        drafts = mark_duplicates(
            db, user_id=batch.user_id, source=batch.source, drafts=drafts, key=key, issues=issues
        )
    else:
        issues.append(
            Issue(
                row_id=None,
                field=None,
                code=ISSUE_NO_ROWS_PARSED,
                message="文件里没有可入账的交易，请确认导出范围和文件格式",
            )
        )

    if utcnow() > deadline_at:
        mark_failed(db, batch, BATCH_TIMEOUT, "批次处理超时，请点击重试", key)
        return

    batch.encrypted_rows = encrypt_json(
        key,
        {
            "rows": [draft.model_dump(mode="json") for draft in drafts],
            "issues": [issue.model_dump(mode="json") for issue in issues],
        },
    )
    batch.encrypted_issues = None
    batch.status = STATUS_PENDING_REVIEW
    batch.progress_current = len(drafts)
    batch.progress_total = len(drafts)
    batch.version += 1
    batch.updated_at = utcnow()
    db.commit()


# ---------------------------------------------------------------- 确认入账


def body_digest(payload) -> str:
    """确认请求体的规范摘要。

    用**校验后的模型**算，不用原始字节：字段顺序、空白、数字写法不同但语义
    相同的两次提交应当算同一个请求，否则客户端的序列化差异会导致假冲突。
    """
    import hashlib

    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def confirm_batch(
    db: Session,
    batch: models.ImportBatch,
    payload,
    settings: Settings,
) -> ConfirmResult:
    """确认入账：幂等 → 状态/版本 → 逐行重校验 → 去重 → 单事务写入。

    顺序不能换（docs/19 3.3）：先查幂等记录，再查版本。反了会把"重放"判成
    "版本冲突"，用户重试一次就再也拿不到原本已经成功的结果。
    """
    key = settings.data_encryption_key
    digest = body_digest(payload)

    # 1) 幂等重放：同 request_id + 同请求体 → 原样返回当时的响应
    if batch.confirmation_request_id:
        if batch.confirmation_request_id != payload.request_id:
            raise ApiError(
                "BATCH_STATE_CONFLICT",
                409,
                "该批次已经确认过，请勿重复提交",
                details=ErrorDetails(current_version=batch.version),
            )
        if batch.request_body_digest != digest:
            raise ApiError("IDEMPOTENCY_CONFLICT", 409, "同一 request_id 不能提交不同内容")
        return _replay_result(batch, key)

    # 2) 状态与期限
    if batch.status != STATUS_PENDING_REVIEW:
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "只有待确认的批次能够确认入账",
            details=ErrorDetails(current_version=batch.version),
        )
    if is_expired(batch):
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "批次草稿已过期，请重新上传该账单",
            details=ErrorDetails(current_version=batch.version),
        )

    # 3) 乐观锁
    if payload.expected_version != batch.version:
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "批次已被修改，请刷新后重试",
            details=ErrorDetails(current_version=batch.version),
        )

    drafts, _issues = load_drafts(batch, key)
    by_row = {draft.row_id: draft for draft in drafts}

    # 4) 逐行重校验。任何一行不合法就整体 422，绝不部分入账
    errors = _validate_rows(payload, by_row)
    if errors:
        raise ApiError(
            "VALIDATION_ERROR",
            422,
            "请修正标红的字段后重试",
            details=ErrorDetails(fields=errors),
        )

    # 5) 去重 + 写入
    created_ids: list[str] = []
    duplicates = 0
    for item in payload.rows:
        txn: TransactionInput = item.transaction
        row_token = row_digest(
            key,
            source=batch.source,
            flow_type=txn.flow_type,
            source_transaction_id=txn.source_transaction_id,
            occurred_at=txn.occurred_at,
            amount_fen=txn.amount_fen,
            merchant=txn.merchant,
            description=txn.description,
        )
        existing = db.scalar(
            select(models.Transaction.id).where(
                models.Transaction.user_id == batch.user_id,
                models.Transaction.dedupe_digest == row_token,
            )
        )
        if existing is not None:
            duplicates += 1
            continue

        # 分类来源必须跟着交易一起进加密区。契约里 Transaction 的
        # classification_source/classification_reason 是必填字段，事后再推断
        # 等于伪造来源（docs/20 第一节明确禁止）。只有用户确实改了类别才标 manual。
        draft = by_row.get(item.row_id)
        stored = txn.model_dump(mode="json")
        stored["ingestion_method"] = batch.ingestion_method
        if draft is None:
            stored["classification_source"] = ClassificationSource.pending.value
            stored["classification_reason"] = ""
        elif txn.category != draft.category:
            stored["classification_source"] = ClassificationSource.manual.value
            stored["classification_reason"] = "用户确认时修正分类"
        else:
            stored["classification_source"] = draft.classification_source.value
            stored["classification_reason"] = draft.classification_reason

        record = models.Transaction(
            id=str(uuid.uuid4()),
            user_id=batch.user_id,
            import_batch_id=batch.id,
            version=1,
            month_index=month_index(txn.occurred_at),
            source=batch.source,
            flow_type=flow_value(txn.flow_type),
            category=txn.category.value,  # type: ignore[union-attr]
            status="confirmed",
            dedupe_digest=row_token,
            encrypted_payload=encrypt_json(key, stored),
        )
        # savepoint：同一次请求里两行内容相同会撞唯一约束，只回滚这一行，
        # 不能把整个确认事务连坐（外层事务要继续写批次状态）
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
        except IntegrityError:
            duplicates += 1
            continue
        created_ids.append(record.id)

    # 6) 批次转 completed，同时把响应快照加密存下来供重放
    result = ConfirmResult(
        batch_id=batch.id,
        created_count=len(created_ids),
        duplicate_count=duplicates,
        ignored_count=max(0, len(drafts) - len(payload.rows)),
        transaction_ids=created_ids,
    )

    batch.status = STATUS_COMPLETED
    batch.version += 1
    batch.updated_at = utcnow()
    batch.confirmation_request_id = payload.request_id
    batch.request_body_digest = digest
    batch.encrypted_confirm_result = encrypt_json(key, result.model_dump(mode="json"))
    db.commit()
    return result


def _replay_result(batch: models.ImportBatch, key: str) -> ConfirmResult:
    """重放返回**当时存下的快照**，不重新计算。

    重新计算会在"用户后来又改了别的数据"的假设下返回不同的数字，那就不是幂等了。
    """
    if not batch.encrypted_confirm_result:
        raise ApiError("IDEMPOTENCY_CONFLICT", 409, "同一 request_id 不能提交不同内容")
    try:
        payload = decrypt_json(key, batch.encrypted_confirm_result)
    except CryptoError:
        raise ApiError(
            "IDEMPOTENCY_CONFLICT", 409, "确认结果快照已损坏，请重新上传该账单"
        ) from None
    return ConfirmResult.model_validate(payload)


def _validate_rows(payload, drafts: dict[str, TransactionDraft]) -> list[FieldError]:
    errors: list[FieldError] = []
    for index, item in enumerate(payload.rows):
        prefix = f"rows[{index}]"
        draft = drafts.get(item.row_id)
        if draft is None:
            errors.append(
                FieldError(
                    field=f"{prefix}.row_id",
                    row_id=item.row_id,
                    code="UNKNOWN_ROW",
                    message="该行不属于当前批次，请刷新后重试",
                )
            )
            continue

        txn = item.transaction
        if txn.occurred_at.tzinfo is None:
            errors.append(
                FieldError(
                    field=f"{prefix}.transaction.occurred_at",
                    row_id=item.row_id,
                    code="TIME_WITHOUT_TIMEZONE",
                    message="交易时间必须带时区，否则无法确定归属月份",
                )
            )
        if not (txn.merchant or "").strip():
            errors.append(
                FieldError(
                    field=f"{prefix}.transaction.merchant",
                    row_id=item.row_id,
                    code="MERCHANT_REQUIRED",
                    message="商户不能为空",
                )
            )
        if draft.duplicate_status == "suspected" and not item.allow_suspected_duplicate:
            # 疑似重复必须用户显式选择。静默跳过会让用户以为记上了，静默入账
            # 则会凭空多一笔，两种都比"让用户点一下"差
            errors.append(
                FieldError(
                    field=f"{prefix}.allow_suspected_duplicate",
                    row_id=item.row_id,
                    code="SUSPECTED_DUPLICATE_NOT_ALLOWED",
                    message="该行疑似重复，请确认是否仍作为新交易入账",
                )
            )
    return errors


def _dedupe_issues(items: list[Issue]) -> list[Issue]:
    seen: set[tuple[str | None, str | None, str, str]] = set()
    unique: list[Issue] = []
    for item in items:
        sig = (item.row_id, item.field, item.code, item.message)
        if sig not in seen:
            seen.add(sig)
            unique.append(item)
    return unique


def resolve_missing_batch(
    db: Session,
    batch: models.ImportBatch,
    payload: ResolveMissingInput,
    settings: Settings,
    provider: IntelligenceProvider,
) -> Batch:
    """根据用户确认的年份或自然语言说明补全缺失字段，重跑确定性判重并返回最新 Batch。"""
    if batch.status != STATUS_PENDING_REVIEW:
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "只有待确认的批次能够补充缺失信息",
            details=ErrorDetails(current_version=batch.version),
        )
    if is_expired(batch):
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "批次草稿已过期，请重新上传该账单",
            details=ErrorDetails(current_version=batch.version),
        )
    if payload.expected_version != batch.version:
        raise ApiError(
            "VERSION_CONFLICT",
            409,
            "批次已被修改，请刷新后重试",
            details=ErrorDetails(current_version=batch.version),
        )

    instruction = (payload.instruction or "").strip() or None
    if payload.default_year is None and instruction is None:
        raise ApiError(
            "VALIDATION_ERROR",
            422,
            "请至少提供默认年份或补充说明",
            details=ErrorDetails(
                fields=[
                    FieldError(
                        field="default_year",
                        row_id=None,
                        code="MISSING_RESOLUTION_INPUT",
                        message="请至少填写默认年份或输入给智能体的补充说明",
                    )
                ]
            ),
        )

    key = settings.data_encryption_key
    drafts, existing_issues = load_drafts(batch, key)
    if any(issue.code == ISSUE_DRAFT_UNREADABLE for issue in existing_issues):
        raise ApiError(
            "SERVICE_UNAVAILABLE",
            503,
            "批次草稿无法解密，请重新上传该账单",
        )

    batch_level_issues = [issue for issue in existing_issues if issue.row_id is None]

    try:
        resolver = getattr(provider, "resolve_missing_fields", None)
        if callable(resolver):
            updated_drafts = resolver(
                drafts,
                default_year=payload.default_year,
                instruction=instruction,
            )
        else:
            updated_drafts = resolve_missing_deterministic(
                drafts,
                default_year=payload.default_year,
                instruction=instruction,
            )
    except IntelligenceFailure as exc:
        raise ApiError("SERVICE_UNAVAILABLE", 503, exc.message) from exc

    cleaned_drafts: list[TransactionDraft] = []
    collected_issues: list[Issue] = list(batch_level_issues)
    for draft in updated_drafts:
        kept_row_issues = [
            issue
            for issue in draft.issues
            if issue.code != ISSUE_DUPLICATE_EXISTING
            and (issue.code != ISSUE_DUPLICATE_SUSPECTED or "同一" in issue.message)
        ]
        intra_duplicate = any(
            issue.code == ISSUE_DUPLICATE_SUSPECTED and "同一" in issue.message
            for issue in kept_row_issues
        )
        cleaned = draft.model_copy(
            update={
                "duplicate_status": "duplicate" if intra_duplicate else "unique",
                "issues": kept_row_issues,
            }
        )
        cleaned_drafts.append(cleaned)
        collected_issues.extend(kept_row_issues)

    marked_drafts = mark_duplicates(
        db,
        user_id=batch.user_id,
        source=batch.source,
        drafts=cleaned_drafts,
        key=key,
        issues=collected_issues,
    )
    final_drafts = [
        draft.model_copy(update={"issues": _dedupe_issues(draft.issues)})
        for draft in marked_drafts
    ]
    final_issues = _dedupe_issues(
        [
            *batch_level_issues,
            *(issue for draft in final_drafts for issue in draft.issues),
        ]
    )

    batch.encrypted_rows = encrypt_json(
        key,
        {
            "rows": [draft.model_dump(mode="json") for draft in final_drafts],
            "issues": [issue.model_dump(mode="json") for issue in final_issues],
        },
    )
    batch.encrypted_issues = None
    batch.version += 1
    batch.updated_at = utcnow()
    db.commit()
    return to_contract(batch, key)


def ensure_pending_state(batch: models.ImportBatch) -> None:
    """retry 的前置校验：只有 failed 且未过期才能重跑。"""
    if batch.status != STATUS_FAILED:
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "只有失败批次能够重试",
            details=ErrorDetails(current_version=batch.version),
        )
    if is_expired(batch):
        raise ApiError(
            "BATCH_STATE_CONFLICT",
            409,
            "批次已过期，请重新上传该账单",
            details=ErrorDetails(current_version=batch.version),
        )


def reset_for_retry(db: Session, batch: models.ImportBatch) -> None:
    """把 failed 批次放回队列。version+1 让客户端的旧页面立即失效。"""
    batch.status = STATUS_UPLOADED
    batch.version += 1
    batch.updated_at = utcnow()
    batch.started_at = None
    batch.progress_current = 0
    batch.progress_total = 0
    batch.encrypted_rows = None
    batch.encrypted_issues = None
    db.commit()


__all__ = [
    "BATCH_EXPIRED",
    "BATCH_INTERRUPTED",
    "BATCH_TIMEOUT",
    "CRYPTO_FAILED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING_REVIEW",
    "STATUS_PROCESSING",
    "STATUS_UPLOADED",
    "UploadTarget",
    "check_content",
    "confirm_batch",
    "create_batch",
    "ensure_pending_state",
    "file_meta",
    "is_expired",
    "load_drafts",
    "load_owned",
    "load_rules",
    "mark_duplicates",
    "mark_failed",
    "process_batch",
    "read_limited",
    "reset_for_retry",
    "resolve_missing_batch",
    "resolve_target",
    "sanitize_filename",
    "to_contract",
]
