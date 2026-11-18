<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChart3,
  BookOpenCheck,
  Check,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  WalletCards,
} from "@lucide/vue";
import { auth, restoreSession, signOut } from "./session";
import { isDemo } from "./api";
import { notice } from "./motion";

const route = useRoute();
const router = useRouter();
const publicPage = computed(() => route.meta.public);
const username = computed(() => auth.session?.user.username ?? "");
const sidebarCollapsed = ref(localStorage.getItem("ledger-sidebar-collapsed") === "true");
const nav = [
  { to: "/report", label: "月度报告", icon: BarChart3 },
  { to: "/transactions", label: "全部账单", icon: WalletCards },
  { to: "/rules", label: "分类规则", icon: BookOpenCheck },
];
const importLink = { to: "/import", label: "导入账单", icon: Plus };
const mobileNav = [nav[0], nav[1], importLink, nav[2]];
const inImport = computed(() => route.path === "/import" || route.path.startsWith("/import/"));

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  localStorage.setItem("ledger-sidebar-collapsed", String(sidebarCollapsed.value));
}
function loginFor(target: { path: string; fullPath: string }) {
  return target.path === "/transactions"
    ? { path: "/login", query: { next: target.fullPath } }
    : { path: "/login" };
}
onMounted(async () => {
  await restoreSession();
  if (!auth.session && !route.meta.public) router.replace(loginFor(route));
});
watch(
  () => auth.session,
  (value) => {
    if (!value && !auth.loading && !route.meta.public) router.replace(loginFor(route));
  },
);
router.beforeEach((to) => {
  if (!auth.loading && !auth.session && !to.meta.public) return loginFor(to);
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
  <div v-else-if="auth.session" class="shell" :class="{ 'is-collapsed': sidebarCollapsed }">
    <aside class="sidebar journal-rail">
      <RouterLink class="brand" to="/report" aria-label="归账，打开月报">
        <span class="brand-mark"><img src="/brand.svg?v=4" alt="" /></span>
        <span class="brand-name">归账</span>
      </RouterLink>
      <RouterLink
        class="rail-import"
        to="/import"
        title="导入账单"
        aria-label="导入账单"
        :aria-current="inImport ? 'page' : undefined"
      >
        <Plus :size="19" /><span>导入账单</span>
      </RouterLink>
      <nav aria-label="主导航" class="nav-list">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-link"
          :aria-label="item.label" :title="item.label">
          <component :is="item.icon" :size="19" :stroke-width="1.75" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="rail-footer">
        <button class="rail-toggle" type="button" :aria-expanded="!sidebarCollapsed"
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleSidebar">
          <component :is="sidebarCollapsed ? PanelLeftOpen : PanelLeftClose" :size="18" />
          <span>收起侧边栏</span>
        </button>
        <div class="profile">
          <span class="avatar" aria-hidden="true">{{ username.slice(0, 1).toUpperCase() }}</span>
          <span class="profile-name">
            <strong :title="username">{{ username }}</strong>
            <small v-if="isDemo">合成数据演示</small>
          </span>
          <button class="icon-btn logout" type="button" aria-label="退出登录" title="退出登录" @click="leave">
            <LogOut :size="17" />
          </button>
        </div>
      </div>
    </aside>
    <nav aria-label="手机主导航" class="mobile-nav">
      <RouterLink v-for="item in mobileNav" :key="item.to" :to="item.to" class="mobile-nav-link"
        :class="{ 'mobile-import': item.to === '/import', 'import-open': item.to === '/import' && inImport }"
        :aria-current="item.to === '/import' && inImport ? 'page' : undefined">
        <span class="mobile-nav-icon"><component :is="item.icon" :size="21" :stroke-width="1.75" /></span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
    <main class="main">
      <div class="page-wrap">
        <RouterView v-slot="{ Component }">
          <Transition name="screen" mode="out-in">
            <div :key="route.path" class="page-screen"><component :is="Component" /></div>
          </Transition>
        </RouterView>
      </div>
    </main>
  </div>
  <Transition name="toast">
    <div v-if="notice" :key="notice.id" class="feedback-toast" role="status">
      <Check :size="18" />{{ notice.text }}
    </div>
  </Transition>
</template>
