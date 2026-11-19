import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";
import "./styles/identity.css";
import "./styles/motion.css";
import "./styles/product.css";
import "./styles/navigation.css";
import "./styles/page-entrance.css";
import { installMotion } from "./motion";
import { revealDirective } from "./directives/reveal";
import { pageEntranceDirective } from "./directives/pageEntrance";

installMotion();
createApp(App)
  .directive("reveal", revealDirective)
  .directive("page-entrance", pageEntranceDirective)
  .use(router)
  .mount("#app");
