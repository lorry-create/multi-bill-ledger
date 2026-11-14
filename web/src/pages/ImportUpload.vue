<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  FileSpreadsheet,
  ImageUp,
  UploadCloud,
  ArrowRight,
} from "@lucide/vue";
import { api } from "../api";
import type { Batch, IngestionMethod, Source } from "../api";
import { AlertTriangle, X } from "@lucide/vue";
import { errorText, withCsrfRetry } from "../session";
import PlatformLogo from "../components/PlatformLogo.vue";
import ParticleField from "../components/ParticleField.vue";

const router = useRouter(),
  source = ref<Source>("wechat"),
  method = ref<IngestionMethod>("file"),
  file = ref<File | null>(null),
  dragging = ref(false),
  busy = ref(false),
  error = ref(""),
  duplicateBatch = ref<Batch | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
function clearFile() {
  file.value = null;
  error.value = "";
  if (fileInput.value) fileInput.value.value = "";
}
const uploadStatusText: Record<Batch["status"], string> = {
  uploaded: "等待处理",
  processing: "正在识别",
  pending_review: "等待确认",
  completed: "已完成入账",
  failed: "处理失败",
};
function formatDupTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
function choose(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null;
  error.value = "";
}
function onDrop(e: DragEvent) {
  dragging.value = false;
  const dropped = e.dataTransfer?.files?.[0] ?? null;
  if (dropped) {
    file.value = dropped;
    error.value = "";
  }
}
function switchMethod(next: IngestionMethod) {
  method.value = next;
  file.value = null;
  dragging.value = false;
  error.value = "";
}
async function submit() {
  if (!file.value) {
    error.value = "请选择需要导入的文件。";
    return;
  }
  const f = file.value;
  const image = method.value === "screenshot";
  if (f.size > (image ? 5 : 10) * 1024 * 1024) {
    error.value = `${image ? "截图不能超过 5 MiB" : "账单文件不能超过 10 MiB"}。`;
    return;
  }
  if (
    !(image
      ? /^image\/(png|jpeg)$/.test(f.type) || /\.(png|jpe?g)$/i.test(f.name)
      : /\.(csv|xlsx)$/i.test(f.name))
  ) {
    error.value = image
      ? "请选择 PNG 或 JPEG 图片。"
      : "请选择 CSV 或 XLSX 文件。";
    return;
  }
  busy.value = true;
  error.value = "";
  duplicateBatch.value = null;
  try {
    const batch = await withCsrfRetry((token) =>
      api.createImport(
        {
          body: { source: source.value, ingestion_method: method.value, file: f },
        },
        token,
      ),
    );
    const hasDupAlert =
      Boolean(batch.duplicate_match) ||
      batch.issues.some(
        (x) =>
          x.code === "DUPLICATE_FILE_UPLOADED" ||
          x.code === "SIMILAR_IMAGE_UPLOADED",
      );
    if (hasDupAlert) {
      duplicateBatch.value = batch;
      return;
    }
    router.push(`/import/${batch.id}`);
  } catch (e) {
    error.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>导入账单</h1>
      <p>把不同平台的记录放在一起，确认后才会进入月报。</p>
    </div>
  </div>
  <div class="upload-layout">
    <section class="upload-main">
      <div class="section-heading">
        <span class="step-dot">1</span>
        <div>
          <h2>选择账单来源</h2>
          <p>请选择文件实际导出的平台</p>
        </div>
      </div>
      <div class="source-grid">
        <button
          class="source-option"
          :class="{ selected: source === 'wechat' }"
          :aria-pressed="source === 'wechat'"
          :disabled="busy"
          @click="source = 'wechat'"
        >
          <PlatformLogo source="wechat" :size="44" />
          <span><strong>微信支付</strong><small>微信账单导出</small></span
          ><span class="radio-dot"></span></button
        ><button
          class="source-option"
          :class="{ selected: source === 'alipay' }"
          :aria-pressed="source === 'alipay'"
          :disabled="busy"
          @click="source = 'alipay'"
        >
          <PlatformLogo source="alipay" :size="44" />
          <span><strong>支付宝</strong><small>支付宝交易记录</small></span
          ><span class="radio-dot"></span>
        </button>
      </div>
      <div class="section-divider"></div>
      <div class="section-heading">
        <span class="step-dot">2</span>
        <div>
          <h2>选择导入方式</h2>
          <p>支持账单文件，也可以上传交易截图</p>
        </div>
      </div>
      <div class="method-tabs">
        <button
          :class="{ active: method === 'file' }"
          :aria-pressed="method === 'file'"
          :disabled="busy"
          @click="switchMethod('file')"
        >
          <FileSpreadsheet :size="18" />账单文件</button
        ><button
          :class="{ active: method === 'screenshot' }"
          :aria-pressed="method === 'screenshot'"
          :disabled="busy"
          @click="switchMethod('screenshot')"
        >
          <ImageUp :size="18" />交易截图
        </button>
      </div>
      <label
        class="dropzone"
        :class="{ dragging, 'has-file': file, 'is-uploading': busy }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        ><input
          ref="fileInput"
          :key="method"
          type="file"
          :aria-label="method === 'file' ? '选择账单文件' : '选择交易截图'"
          :disabled="busy"
          :accept="
            method === 'file'
              ? '.csv,.xlsx'
              : '.png,.jpg,.jpeg,image/png,image/jpeg'
          "
          @change="choose"
        /><span class="upload-icon"
          ><UploadCloud :size="28" :stroke-width="1.6" /></span
        ><strong>{{ file?.name ?? "点击或拖拽文件到此处" }}</strong
        ><span>{{
          method === "file"
            ? "CSV、XLSX，单个文件不超过 10 MiB"
            : "PNG、JPEG，单张图片不超过 5 MiB"
        }}</span></label
      >
      <div v-if="file" class="selected-file" role="status"><FileSpreadsheet v-if="method === 'file'" :size="19" /><ImageUp v-else :size="19" /><span><strong>{{ file.name }}</strong><small>{{ (file.size / 1024).toFixed(1) }} KB · {{ busy ? '上传处理中' : '已就绪，等待导入' }}</small></span><button type="button" class="icon-btn" aria-label="移除已选文件" :disabled="busy" @click="clearFile"><X :size="17" /></button></div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="upload-action">
        <button class="primary-btn" :disabled="busy" @click="submit">
          {{ busy ? "正在上传…" : "开始导入" }} <ArrowRight :size="18" />
        </button>
      </div>
    </section>
    <aside class="upload-aside">
      <ParticleField />
      <h3>导入后会发生什么？</h3>
      <ol>
        <li>
          <span>01</span>
          <div>
            <strong>识别账单内容</strong>
            <p>读取时间、金额、商户和收支方向。</p>
          </div>
        </li>
        <li>
          <span>02</span>
          <div>
            <strong>逐笔核对</strong>
            <p>检查缺失字段、分类与重复交易。</p>
          </div>
        </li>
        <li>
          <span>03</span>
          <div>
            <strong>确认入账</strong>
            <p>只有你确认的记录才进入账本和月报。</p>
          </div>
        </li>
      </ol>
      <div class="aside-foot">原始文件仅供当前账号查看</div>
    </aside>
  </div>
  <div
    v-if="duplicateBatch"
    class="modal-backdrop"
    @click.self="duplicateBatch = null"
  >
    <section
      class="edit-dialog dup-upload-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="重复账单上传提醒"
    >
      <div class="dialog-head">
        <div>
          <h2 class="dup-upload-title">
            <AlertTriangle :size="18" />
            {{
              duplicateBatch.duplicate_match?.match_type === "similar_image"
                ? "检测到高度相似的账单截图"
                : "检测到此前已上传过该账单"
            }}
          </h2>
          <p>为避免同一笔交易被重复记入账本，请先确认是否需要继续导入。</p>
        </div>
        <button
          class="icon-btn"
          aria-label="关闭"
          @click="duplicateBatch = null"
        >
          <X :size="20" />
        </button>
      </div>

      <div v-if="duplicateBatch.duplicate_match" class="dup-upload-box">
        <p>
          <strong>历史文件：</strong>{{ duplicateBatch.duplicate_match.file_name }}
        </p>
        <p>
          <strong>上次上传：</strong
          >{{ formatDupTime(duplicateBatch.duplicate_match.created_at) }}
        </p>
        <p>
          <strong>批次状态：</strong
          >{{ uploadStatusText[duplicateBatch.duplicate_match.status] }}
          （{{
            duplicateBatch.duplicate_match.created_count > 0
              ? `已正式入账 ${duplicateBatch.duplicate_match.created_count} 笔`
              : "尚未正式入账"
          }}）
        </p>
      </div>
      <div v-else class="dup-upload-box">
        <p>
          {{
            duplicateBatch.issues
              .map((i) => i.message)
              .join("；") || "该账单与历史上传重合，请注意核对。"
          }}
        </p>
      </div>

      <div class="dialog-actions">
        <button
          type="button"
          class="secondary-btn"
          @click="router.push('/transactions')"
        >
          查看已入账单
        </button>
        <button
          v-if="duplicateBatch.duplicate_match"
          type="button"
          class="secondary-btn"
          @click="
            router.push(`/import/${duplicateBatch.duplicate_match.batch_id}`)
          "
        >
          查看历史批次
        </button>
        <button
          type="button"
          class="primary-btn"
          @click="router.push(`/import/${duplicateBatch.id}`)"
        >
          仍要前往逐笔核对
        </button>
      </div>
    </section>
  </div>
</template>
<style scoped>
.dup-upload-dialog {
  width: min(100%, 560px);
}
.dup-upload-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b25200;
}
.dup-upload-box {
  display: grid;
  gap: 6px;
  margin: 12px 0 18px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #fff7ea;
  border: 1px solid #f2c474;
  font-size: 13px;
  color: #7c4a03;
}
.dup-upload-box p {
  margin: 0;
}
</style>
