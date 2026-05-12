import { DASHBOARD_CLIENT_SCRIPT } from "./static-client.js";
import { DASHBOARD_MARKUP } from "./static-markup.js";
import { DASHBOARD_STYLES } from "./static-styles.js";

export function renderDashboardHtml(): string {
  return String.raw`<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AF 투자 연구 대시보드</title>
  <style>
${DASHBOARD_STYLES}
  </style>
</head>
<body>${DASHBOARD_MARKUP}  <script>
${DASHBOARD_CLIENT_SCRIPT}
  </script>
</body>
</html>`;
}
