import { csvParseRows } from "d3-dsv";
import writeXlsxFile from "write-excel-file/browser";
import type { CellObject, SheetData } from "write-excel-file/browser";

const columns: Record<string, { label: string; width: number }> = {
  occurred_at: { label: "交易时间", width: 30 },
  source: { label: "平台", width: 13 },
  flow_type: { label: "收支方向", width: 13 },
  category: { label: "类别", width: 15 },
  amount_fen: { label: "金额（分）", width: 17 },
  currency: { label: "币种", width: 10 },
  merchant: { label: "商户", width: 24 },
  description: { label: "摘要与备注", width: 35 },
  classification_source: { label: "分类来源", width: 19 },
  source_transaction_id: { label: "平台交易号", width: 31 },
};

export async function transactionWorkbook(csv: Blob): Promise<Blob> {
  const [headers, ...rows] = csvParseRows(
    (await csv.text()).replace(/^\uFEFF/, ""),
  );
  if (
    !headers?.includes("amount_fen") ||
    rows.some((row) => row.length !== headers.length)
  ) {
    throw new Error("导出的 CSV 列不完整");
  }
  const data: SheetData = [
    headers.map((key) => ({
      value: columns[key]?.label ?? key,
      fontWeight: "bold",
      backgroundColor: "#E9F2FC",
    })),
  ];
  for (const row of rows) {
    data.push(
      row.map((value, index): CellObject => {
        // Excel 数字最多精确表示 15 位。更长的金额和平台交易号保留为文本。
        if (headers[index] === "amount_fen" && /^\d{1,15}$/.test(value)) {
          return { value: Number(value), type: Number };
        }
        return { value, type: String };
      }),
    );
  }
  return writeXlsxFile(data, {
    sheet: "账单明细",
    columns: headers.map((key) => ({ width: columns[key]?.width ?? 18 })),
  }).toBlob();
}
