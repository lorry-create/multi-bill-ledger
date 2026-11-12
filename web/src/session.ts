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
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      auth.session = null;
      return "登录已过期，请重新登录。";
    }
    if (error.status === 409) return "数据已更新，请刷新后核对再保存。";
    if (error.status === 413) return "文件超过上传大小限制。";
    if (error.status === 415)
      return "文件格式暂不支持，请使用 CSV、XLSX、PNG 或 JPEG。";
    if (error.status === 503) return "服务暂时不可用，请稍后重试。";
    return error.payload?.error?.message || `请求失败（${error.status}）`;
  }
  return isDemo
    ? "演示操作失败，请重试。"
    : "无法连接服务，请检查后端是否运行。";
}
