// Compile-time checks only. This function is not executed.
import {getMonthlyReport, patchTransaction, confirmImport, createImport, putBudget} from './client.generated';
function compileExamples(): void {
  void getMonthlyReport({query:{month:'2026-11'}});
  void patchTransaction({path:{id:'t1'},body:{expected_version:1,changes:{category:'dining'}}},'synthetic');
  void createImport({body:{source:'wechat',ingestion_method:'file',file:new Blob(['synthetic'])}},'synthetic');
  // @ts-expect-error month query is required
  void getMonthlyReport({});
  // @ts-expect-error money is integer fen represented as number, not a currency string
  void patchTransaction({path:{id:'t1'},body:{expected_version:1,changes:{amount_fen:'23.00'}}},'synthetic');
  // @ts-expect-error shared category codes cannot be replaced by translated labels
  void patchTransaction({path:{id:'t1'},body:{expected_version:1,changes:{category:'餐饮'}}},'synthetic');
  // @ts-expect-error expected_version is required by ConfirmInput
  void confirmImport({path:{id:'b1'},body:{request_id:'synthetic',rows:[]}},'synthetic');
  // @ts-expect-error budgets require a resolved category, not pending
  void putBudget({body:{month:'2026-11',category:'pending',amount_fen:0}},'synthetic');
}
void compileExamples;
