const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const DESIGN_DIR = path.join(ROOT, "docs", "6.2-design");
const ASSET_DIR = path.join(DESIGN_DIR, "assets");
const PROTOTYPE = path.join(DESIGN_DIR, "prototype", "index.html");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

const MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

async function readMermaidBlocks(file) {
  const text = await fs.readFile(file, "utf8");
  return [...text.matchAll(/```mermaid\n([\s\S]*?)```/g)].map((match) => match[1].trim());
}

function diagramName(source) {
  if (source.includes("STUDENT_IMPORT_BATCHES")) return "er-identity";
  if (source.includes("HANDOVER_RECORDS") && source.includes("ITEM_IMAGES")) return "er-circulation";
  if (source.includes("CHARITY_RECEIPT_ITEMS")) return "er-charity";
  if (source.includes("DISPUTE_MESSAGES") && source.includes("AUDIT_LOGS")) return "er-governance";
  if (source.includes("Jinja2 页面")) return "architecture-layers";
  if (source.includes("借用路由") || source.includes("提交借用申请")) return "dataflow-borrow";
  if (source.includes("公益路由") || source.includes("站点管理员创建项目需求")) return "dataflow-charity";
  return null;
}

async function renderMermaid(browser, source, outputPath) {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1100 },
    deviceScaleFactor: 1.5,
  });
  await page.setContent(
    `<!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <style>
        html, body { margin: 0; background: #fffdf8; }
        body { padding: 28px; font-family: "Microsoft YaHei", sans-serif; }
        #diagram { display: inline-block; min-width: 720px; }
        .mermaid { color: #24312a; }
      </style>
    </head>
    <body>
      <div id="diagram"><pre class="mermaid">${source
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")}</pre></div>
      <script type="module">
        import mermaid from "${MERMAID_CDN}";
        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          securityLevel: "strict",
          fontFamily: "Microsoft YaHei, sans-serif",
          themeVariables: {
            primaryColor: "#edf4ec",
            primaryTextColor: "#24312a",
            primaryBorderColor: "#235a3b",
            lineColor: "#6f8174",
            secondaryColor: "#fff4e8",
            tertiaryColor: "#f7f2e8",
            noteBkgColor: "#fff7e9",
            noteBorderColor: "#b66a3c"
          },
          flowchart: { htmlLabels: true, curve: "basis", padding: 18 },
          er: { diagramPadding: 28, layoutDirection: "TB", minEntityWidth: 120, minEntityHeight: 54 }
        });
        await mermaid.run({ querySelector: ".mermaid" });
        document.documentElement.dataset.ready = "1";
      </script>
    </body>
    </html>`,
    { waitUntil: "networkidle" }
  );
  await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, {
    timeout: 30000,
  });
  await page.locator("#diagram").screenshot({ path: outputPath });
  await page.close();
}

async function renderPrototype(browser, query, outputName, viewport) {
  const page = await browser.newPage({
    viewport,
    deviceScaleFactor: 1.25,
  });
  const url = `${pathToFileURL(PROTOTYPE).href}?${query}&capture=1`;
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(200);
  await page.screenshot({
    path: path.join(ASSET_DIR, outputName),
    fullPage: true,
  });
  await page.close();
}

async function main() {
  await fs.mkdir(ASSET_DIR, { recursive: true });
  const browser = await chromium.launch({
    executablePath: EDGE,
    headless: true,
    args: ["--allow-file-access-from-files"],
  });

  try {
    const dataModelBlocks = await readMermaidBlocks(path.join(DESIGN_DIR, "01-data-model-and-er.md"));
    const architectureBlocks = await readMermaidBlocks(path.join(DESIGN_DIR, "03-architecture-design.md"));
    for (const source of [...dataModelBlocks, ...architectureBlocks]) {
      const name = diagramName(source);
      if (!name) continue;
      await renderMermaid(browser, source, path.join(ASSET_DIR, `${name}.png`));
    }

    const desktop = { width: 1440, height: 1000 };
    const mobile = { width: 390, height: 844 };
    await renderPrototype(browser, "view=role", "ui-role-select.png", desktop);
    await renderPrototype(
      browser,
      "view=context&role=student&school=4151010610",
      "ui-school-campus.png",
      desktop
    );
    await renderPrototype(browser, "view=discover&variant=A", "ui-list-a.png", desktop);
    await renderPrototype(browser, "view=discover&variant=B", "ui-list-b.png", desktop);
    await renderPrototype(browser, "view=discover&variant=C", "ui-list-c.png", desktop);
    await renderPrototype(browser, "view=discover&variant=A", "ui-list-mobile.png", mobile);
    await renderPrototype(browser, "view=item", "ui-item-detail.png", desktop);
    await renderPrototype(browser, "view=create", "ui-create-item.png", desktop);
    await renderPrototype(browser, "view=request", "ui-request-status.png", desktop);
    await renderPrototype(browser, "view=donate", "ui-donation-form.png", desktop);
    await renderPrototype(browser, "view=charity", "ui-charity.png", desktop);
    await renderPrototype(browser, "view=station", "ui-station-dashboard.png", desktop);
    await renderPrototype(browser, "view=admin", "ui-admin-import.png", desktop);
    await renderPrototype(
      browser,
      "view=login&role=student&school=4151010610&campus=WANGJIANG",
      "ui-login.png",
      desktop
    );
    await renderPrototype(
      browser,
      "view=register&school=4151010610&campus=WANGJIANG",
      "ui-register.png",
      desktop
    );
    await renderPrototype(browser, "view=login&role=station", "ui-login-station.png", desktop);
    await renderPrototype(browser, "view=login&role=admin", "ui-login-platform.png", desktop);
    await renderPrototype(
      browser,
      "view=login&role=university_admin",
      "ui-login-university-admin.png",
      desktop
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
