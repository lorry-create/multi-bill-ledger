<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChart3,
  BookOpenCheck,
  Check,
  LogOut,
  ChevronDown,
  Menu,
  X,
  Plus,
  WalletCards,
} from "@lucide/vue";
import { auth, restoreSession, signOut } from "./session";
import { isDemo } from "./api";
import { notice } from "./motion";
import BrandMark from "./components/BrandMark.vue";

const route = useRoute();
const router = useRouter();
const publicPage = computed(() => route.meta.public);
const username = computed(() => auth.session?.user.username ?? "");
const menuOpen = ref(false);
const accountOpen = ref(false);
const header = ref<HTMLElement>();
const menuButton = ref<HTMLButtonElement>();
const accountButton = ref<HTMLButtonElement>();
const compactNavigation = window.matchMedia("(max-width: 900px)");
const nav = [
  { to: "/report", label: "月度报告", icon: BarChart3 },
  { to: "/transactions", label: "全部账单", icon: WalletCards },
  { to: "/rules", label: "分类规则", icon: BookOpenCheck },
];
const importLink = { to: "/import", label: "导入账单", icon: Plus };
const mobileNav = [...nav, importLink];
const inImport = computed(
  () => route.path === "/import" || route.path.startsWith("/import/"),
);

function closeOnOutside(event: PointerEvent) {
  if (header.value?.contains(event.target as Node)) return;
  menuOpen.value = false;
  accountOpen.value = false;
}
function onNavigationResize(event: MediaQueryListEvent) {
  if (!event.matches) menuOpen.value = false;
}
function onEscape(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (accountOpen.value) {
    accountOpen.value = false;
    accountButton.value?.focus();
  } else if (menuOpen.value) {
    menuOpen.value = false;
    menuButton.value?.focus();
  }
}
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false;
    accountOpen.value = false;
  },
);
onMounted(() => {
  document.addEventListener("pointerdown", closeOnOutside);
  document.addEventListener("keydown", onEscape);
  compactNavigation.addEventListener("change", onNavigationResize);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closeOnOutside);
  document.removeEventListener("keydown", onEscape);
  compactNavigation.removeEventListener("change", onNavigationResize);
});
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
    if (!value && !auth.loading && !route.meta.public)
      router.replace(loginFor(route));
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
  <div v-else-if="auth.session" class="shell horizontal-shell">
    <a class="skip-to-content" href="#workspace-content">跳到主要内容</a>
    <header ref="header" class="workspace-header">
      <div class="workspace-header-inner">
        <RouterLink
          class="workspace-brand"
          to="/report"
          aria-label="归账，打开月报"
          @click="
            menuOpen = false;
            accountOpen = false;
          "
        >
          <BrandMark class="workspace-brand-mark" animated />
          <span class="workspace-brand-copy"
            ><strong>归账</strong><small>把每一笔，归于清晰</small></span
          >
        </RouterLink>
        <nav aria-label="主导航" class="workspace-nav">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="workspace-link"
            @click="accountOpen = false"
            >{{ item.label }}</RouterLink
          >
        </nav>
        <div class="workspace-actions">
          <RouterLink
            to="/import"
            class="workspace-import"
            @click="
              menuOpen = false;
              accountOpen = false;
            "
            :aria-current="inImport ? 'page' : undefined"
            ><Plus :size="17" /><span>导入账单</span></RouterLink
          >
          <div class="workspace-account">
            <button
              ref="accountButton"
              class="workspace-account-toggle"
              type="button"
              aria-label="账号菜单"
              aria-controls="account-panel"
              :aria-expanded="accountOpen"
              @click="
                accountOpen = !accountOpen;
                menuOpen = false;
              "
            >
              <span class="workspace-avatar" aria-hidden="true">{{
                username.slice(0, 1).toUpperCase()
              }}</span>
              <span class="workspace-username">{{ username }}</span
              ><ChevronDown :size="14" :class="{ 'is-open': accountOpen }" />
            </button>
            <Transition name="nav-panel">
              <div
                v-if="accountOpen"
                id="account-panel"
                class="workspace-account-panel"
              >
                <p>
                  <strong>{{ username }}</strong
                  ><small>{{ isDemo ? "合成数据演示" : "个人账本" }}</small>
                </p>
                <button type="button" @click="leave">
                  <LogOut :size="16" />退出登录
                </button>
              </div>
            </Transition>
          </div>
          <button
            ref="menuButton"
            class="workspace-menu-toggle"
            type="button"
            :aria-label="menuOpen ? '收起导航' : '展开导航'"
            aria-controls="mobile-navigation"
            :aria-expanded="menuOpen"
            @click="
              menuOpen = !menuOpen;
              accountOpen = false;
            "
          >
            <component :is="menuOpen ? X : Menu" :size="21" />
          </button>
        </div>
      </div>
      <Transition name="nav-panel">
        <nav
          v-if="menuOpen"
          id="mobile-navigation"
          class="workspace-mobile-nav"
          aria-label="手机主导航"
        >
          <RouterLink
            v-for="item in mobileNav"
            :key="item.to"
            :to="item.to"
            @click="menuOpen = false"
            :aria-current="
              item.to === '/import' && inImport ? 'page' : undefined
            "
            ><component :is="item.icon" :size="19" /><span>{{
              item.label
            }}</span></RouterLink
          >
        </nav>
      </Transition>
    </header>
    <main id="workspace-content" class="main" tabindex="-1">
      <div class="page-wrap">
        <RouterView v-slot="{ Component }">
          <Transition name="screen" mode="out-in">
            <div :key="route.path" v-page-entrance class="page-screen">
              <component :is="Component" />
            </div>
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
