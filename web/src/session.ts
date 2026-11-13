import { reactive } from "vue";
import { api, ApiError, isDemo } from "./api";
import type { Session } from "./api";

export const auth = reactive<{ session: Session | null; loading: boolean }>({
  session: null,
  loading: true,
});
export async function restoreSession() {
  try {
    auth.session = await api.getSession({});
  } catch {
    auth.session = null;
  } finally {
    auth.loading = false;
  }
}
export async function signIn(username: string, password: string) {
  await api.login({ body: { username, password } });
  auth.session = await api.getSession({});
}
export async function signOut() {
  try {
    await api.logout({}, auth.session?.csrf_token);
  } finally {
    auth.session = null;
  }
}
export const csrf = () => auth.session?.csrf_token ?? "";
export async function withCsrfRetry<T>(run: (token: string) => Promise<T>): Promise<T> {
  try {
    return await run(csrf());
  } catch (e) {
    if (
      e instanceof ApiError &&
      e.status === 403 &&
      e.payload?.error?.code === "CSRF_INVALID"
    ) {
      await restoreSession();
      if (auth.session) return await run(csrf());
    }
    throw e;
  }
}
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const code = error.payload?.error?.code;
    const details = error.payload?.error?.details;
    if (error.status === 401) {
      auth.session = null;
      if (code === "AUTH_INVALID" || code === "ACCOUNT_DISABLED")
        return error.payload?.error?.message || "账号或密码不正确。";
      return "登录已过期，请重新登录。";
    }
    if (error.status === 429 || code === "LOGIN_LOCKED") {
      const wait = details?.retry_after_seconds;
      return wait
        ? `登录失败次数过多，请在 ${wait} 秒后再试。`
        : error.payload?.error?.message || "操作过于频繁，请稍后再试。";
    }
    if (code === "VERSION_CONFLICT") {
      const ver = details?.current_version;
      return ver !== undefined && ver !== null
        ? `数据已被其他操作修改（当前最新 v${ver}），请刷新核对后再提交。`
        : "数据已被其他操作修改，请刷新核对后再提交。";
    }
    if (code === "BATCH_STATE_CONFLICT" || code === "IDEMPOTENCY_CONFLICT")
      return error.payload?.error?.message || "当前批次状态不允许该操作，请刷新确认。";
    if (error.status === 409)
      return error.payload?.error?.message || "数据已更新，请刷新后核对再保存。";
    if (error.status === 413) return "文件超过上传大小限制。";
    if (error.status === 415)
      return "文件格式暂不支持，请使用 CSV、XLSX、PNG 或 JPEG。";
    if (code === "EXPORT_UNAVAILABLE" || error.status === 503)
      return error.payload?.error?.message || "服务暂时不可用，请稍后重试。";
    return error.payload?.error?.message || `请求失败（${error.status}）`;
  }
  return isDemo
    ? "演示操作失败，请重试。"
    : "无法连接服务，请检查后端是否运行。";
}
