import * as real from "./client.generated";
import { mock } from "./mock";

export const isDemo = import.meta.env.VITE_USE_MOCK === "true";
export const api = (isDemo ? mock : real) as typeof real;
export { ApiError } from "./client.generated";
export type * from "./client.generated";
