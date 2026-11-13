import type {
  Category,
  ClassificationSource,
  FlowType,
  Source,
} from "./api/client.generated";

export const categories: Record<Category, string> = {
  dining: "餐饮",
  transport: "交通",
  shopping: "购物",
  salary: "工资",
  housing: "居住",
  entertainment: "娱乐",
  health: "医疗",
  education: "教育",
  other: "其他",
  pending: "待确认",
};
export const classificationSources: Record<ClassificationSource, string> = {
  user_rule: "个人规则",
  general_rule: "通用规则",
  deepseek: "DeepSeek 分类",
  manual: "手动选择",
  pending: "待选类别",
};
export const flows: Record<FlowType, string> = {
  income: "收入",
  expense: "支出",
  refund: "退款",
  transfer: "转账",
  repayment: "还款",
};
export const sources: Record<Source, string> = {
  alipay: "支付宝",
  wechat: "微信支付",
};
export const yuan = (fen: number) =>
  new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(
    fen / 100,
  );
export const dateTime = (date: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
export const toLocalInput = (date: string | null) =>
  date
    ? new Date(new Date(date).getTime() + 8 * 3600_000)
        .toISOString()
        .slice(0, 16)
    : "";
export const fromLocalInput = (date: string) =>
  date ? `${date}:00+08:00` : "";
export function parseYuan(value: string, allowZero = false): number | null {
  if (!/^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  const fen = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return fen > 0 || allowZero ? fen : null;
}
export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
