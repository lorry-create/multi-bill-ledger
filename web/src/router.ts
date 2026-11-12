import { createRouter, createWebHistory } from "vue-router";
import Login from "./pages/Login.vue";
import ImportUpload from "./pages/ImportUpload.vue";
import ImportConfirm from "./pages/ImportConfirm.vue";
import Transactions from "./pages/Transactions.vue";
import Report from "./pages/Report.vue";
import Rules from "./pages/Rules.vue";

export default createRouter({
  history: createWebHistory(),
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
