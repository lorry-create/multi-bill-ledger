import { createRouter, createWebHistory } from "vue-router";
import Login from "./pages/Login.vue";
import ImportUpload from "./pages/ImportUpload.vue";
import ImportConfirm from "./pages/ImportConfirm.vue";
import Transactions from "./pages/Transactions.vue";
import Report from "./pages/Report.vue";
import Rules from "./pages/Rules.vue";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, saved) {
    if (!saved) return to.path !== from.path ? { top: 0, behavior: "instant" } : false;
    if (to.path !== "/report" || !saved.top) return { ...saved, behavior: "instant" };
    // 月报返回时，先等接口数据撑开页面，再恢复离开时的位置。
    return new Promise((resolve) => {
      const finish = (restore: boolean) => {
        observer.disconnect();
        clearTimeout(timeout);
        window.removeEventListener("wheel", cancel);
        window.removeEventListener("touchstart", cancel);
        resolve(restore ? { ...saved, behavior: "instant" } : false);
      };
      const cancel = () => finish(false);
      const check = () => {
        if (router.currentRoute.value.fullPath !== to.fullPath) cancel();
        else if (document.querySelector(".monthly-statement[aria-busy='false']")) finish(true);
      };
      const observer = new MutationObserver(check);
      const timeout = window.setTimeout(cancel, 10000);
      observer.observe(document.getElementById("app")!, {
        childList: true, subtree: true, attributes: true, attributeFilter: ["aria-busy"],
      });
      window.addEventListener("wheel", cancel, { passive: true });
      window.addEventListener("touchstart", cancel, { passive: true });
      check();
    });
  },
  routes: [
    { path: "/login", component: Login, meta: { public: true } },
    { path: "/", redirect: "/report" },
    { path: "/import", component: ImportUpload },
    { path: "/import/:id", component: ImportConfirm },
    { path: "/transactions", component: Transactions },
    { path: "/report", component: Report },
    { path: "/rules", component: Rules },
    { path: "/:pathMatch(.*)*", redirect: "/report" },
  ],
});
export default router;
