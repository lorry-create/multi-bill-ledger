<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowDownToLine,
  BarChart3,
  BookOpenCheck,
  ChevronRight,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
  WalletCards,
} from "@lucide/vue";
import { auth, restoreSession, signOut } from "./session";
import { isDemo } from "./api";

const route = useRoute(),
  router = useRouter();
const publicPage = computed(() => route.meta.public);
const sidebarCollapsed = ref(localStorage.getItem("ledger-sidebar-collapsed") === "true");
const mobileMenuOpen = ref(false);
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  localStorage.setItem("ledger-sidebar-collapsed", String(sidebarCollapsed.value));
}
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
  mobileMenuOpen.value = false;
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
  <div v-else class="shell" :class="{ 'is-collapsed': sidebarCollapsed }">
    <aside class="sidebar">
      <RouterLink class="brand" to="/report"
        ><span class="brand-mark"><img src="/brand.svg" alt="" /></span
        ><span class="brand-name">归账</span></RouterLink
      >
      <div class="side-caption">个人账务空间</div>
      <nav aria-label="主导航" class="nav-list">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :title="item.label"
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
      <button class="mobile-menu-toggle" type="button" :aria-expanded="mobileMenuOpen" aria-label="打开菜单" @click="mobileMenuOpen = true"><Menu :size="22" /></button>
    </aside>
    <div v-if="mobileMenuOpen" class="mobile-drawer-backdrop" @click.self="mobileMenuOpen = false">
      <section class="mobile-drawer" aria-label="导航菜单">
        <div class="drawer-heading"><strong>归账</strong><button type="button" class="icon-btn" aria-label="关闭菜单" @click="mobileMenuOpen = false"><X :size="21" /></button></div>
        <p class="drawer-user">{{ auth.session?.user.username }}</p>
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="drawer-link" @click="mobileMenuOpen = false"><component :is="item.icon" :size="19" />{{ item.label }}</RouterLink>
        <button class="drawer-logout" type="button" @click="leave"><LogOut :size="18" />退出登录</button>
      </section>
    </div>
    <nav aria-label="手机主导航" class="mobile-nav">
      <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="mobile-nav-link">
        <component :is="item.icon" :size="21" :stroke-width="1.8" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
    <main class="main">
      <header class="topbar">
        <div class="topbar-leading"><button class="icon-btn sidebar-toggle" type="button" :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar"><PanelLeftOpen v-if="sidebarCollapsed" :size="20" /><PanelLeftClose v-else :size="20" /></button><span class="breadcrumb"
          >归账 <ChevronRight :size="14" />
          {{
            nav.find((x) => route.path.startsWith(x.to))?.label ?? "导入确认"
          }}</span></div>
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
      <div class="page-wrap">
        <RouterView v-slot="{ Component }">
          <Transition name="screen" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </div>
    </main>
  </div>
</template>
