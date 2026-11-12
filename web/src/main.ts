import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";
import "./styles/identity.css";
import "./styles/motion.css";

createApp(App).use(router).mount("#app");
