import { render } from "preact";
import App from "./classic-app";

const root = document.getElementById("app");
if (!root) throw new Error("Lyoko root element missing");
render(<App />, root);
