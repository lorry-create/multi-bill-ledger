import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";
import "./styles/identity.css";
import "./styles/motion.css";
import "./styles/product.css";
import { installMotion } from "./motion";

installMotion();
createApp(App).use(router).mount("#app");
