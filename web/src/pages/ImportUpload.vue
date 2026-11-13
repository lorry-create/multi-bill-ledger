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
import type { IngestionMethod, Source } from "../api";
import { errorText, withCsrfRetry } from "../session";

const router = useRouter(),
  source = ref<Source>("wechat"),
  method = ref<IngestionMethod>("file"),
  file = ref<File | null>(null),
  dragging = ref(false),
  busy = ref(false),
  error = ref("");
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
  try {
    const batch = await withCsrfRetry((token) =>
      api.createImport(
        {
          body: { source: source.value, ingestion_method: method.value, file: f },
        },
        token,
      ),
    );
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
          @click="source = 'wechat'"
        >
          <span class="source-logo wechat-logo">微</span
          ><span><strong>微信支付</strong><small>微信账单导出</small></span
          ><span class="radio-dot"></span></button
        ><button
          class="source-option"
          :class="{ selected: source === 'alipay' }"
          @click="source = 'alipay'"
        >
          <span class="source-logo alipay-logo">支</span
          ><span><strong>支付宝</strong><small>支付宝交易记录</small></span
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
          @click="switchMethod('file')"
        >
          <FileSpreadsheet :size="18" />账单文件</button
        ><button
          :class="{ active: method === 'screenshot' }"
          @click="switchMethod('screenshot')"
        >
          <ImageUp :size="18" />交易截图
        </button>
      </div>
      <label
        class="dropzone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        ><input
          :key="method"
          type="file"
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
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="upload-action">
        <button class="primary-btn" :disabled="busy" @click="submit">
          {{ busy ? "正在上传…" : "开始导入" }} <ArrowRight :size="18" />
        </button>
      </div>
    </section>
    <aside class="upload-aside">
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
</template>
