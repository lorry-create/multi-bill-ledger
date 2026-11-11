<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowDownToLine,
  BarChart3,
  BookOpenCheck,
  ChevronRight,
  LogOut,
  PanelLeftClose,
  WalletCards,
} from "@lucide/vue";
import { auth, restoreSession, signOut } from "./session";
import { isDemo } from "./api";

const route = useRoute(),
  router = useRouter();
const publicPage = computed(() => route.meta.public);
const nav = [
  { to: "/report", label: "月度概览", icon: BarChart3 },
  { to: "/transactions", label: "全部账单", icon: WalletCards },
  { to: "/import", label: "导入账单", icon: ArrowDownToLine },
  { to: "/rules", label: "分类规则", icon: BookOpenCheck },
];
onMounted(async () => {
  await restoreSession();
  if (!auth.session && !route.meta.public) router.replace("/login");
});
watch(
  () => auth.session,
  (value) => {
    if (!value && !auth.loading && !route.meta.public) router.replace("/login");
  },
);
router.beforeEach((to) => {
  if (!auth.loading && !auth.session && !to.meta.public) return "/login";
  if (auth.session && to.path === "/login") return "/report";
});
async function leave() {
  try {
    await signOut();
  } finally {
    router.push("/login");
  }
}
</script>

<template>
  <div v-if="auth.loading" class="startup">正在打开归账…</div>
  <RouterView v-else-if="publicPage" />
  <div v-else class="shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/report"
        ><span class="brand-mark"
          ><PanelLeftClose :size="22" :stroke-width="2" /></span
        ><span>归账<span class="brand-dot">.</span></span></RouterLink
      >
      <div class="side-caption">个人账务空间</div>
      <nav aria-label="主导航" class="nav-list">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          ><component :is="item.icon" :size="18" :stroke-width="1.8" /><span>{{
            item.label
          }}</span
          ><ChevronRight class="nav-chevron" :size="16"
        /></RouterLink>
      </nav>
      <div class="side-bottom">
        <div class="profile">
          <span class="avatar">{{
            auth.session?.user.username.slice(0, 1).toUpperCase()
          }}</span
          ><span class="profile-name"
            ><strong>{{ auth.session?.user.username }}</strong
            ><small>{{ isDemo ? "合成数据演示" : "我的账本" }}</small></span
          ><button
            class="icon-btn logout"
            type="button"
            aria-label="退出登录"
            title="退出登录"
            @click="leave"
          >
            <LogOut :size="17" />
          </button>
        </div>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <span class="breadcrumb"
          >归账 <ChevronRight :size="14" />
          {{
            nav.find((x) => route.path.startsWith(x.to))?.label ?? "导入确认"
          }}</span
        >
        <div class="top-actions">
          <span v-if="isDemo" class="demo-badge">合成数据演示</span
          ><span class="top-date">{{
            new Intl.DateTimeFormat("zh-CN", {
              month: "long",
              day: "numeric",
            }).format(new Date())
          }}</span>
        </div>
      </header>
      <div class="page-wrap"><RouterView /></div>
    </main>
  </div>
</template>
