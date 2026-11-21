const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const ROOT = path.resolve(__dirname, "..");
const PROTOTYPE = path.join(ROOT, "docs", "6.2-design", "prototype", "index.html");
const ASSET_DIR = path.join(ROOT, "docs", "6.2-design", "assets");
const REPORT = path.join(ROOT, "docs", "6.2-design", "evidence", "ui-browser-report.json");
const RESPONSIVE_DIR = path.join(ROOT, ".qa", "6.2-ui-responsive");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PROFILE = path.join(ROOT, ".qa", `edge-ui-${process.pid}-${Date.now()}`);

const desktop = { width: 1440, height: 1000 };
const mobile = { width: 390, height: 844 };
const targets = [
  ["ui-role-select.png", "view=role", desktop],
  ["ui-school-campus.png", "view=context&role=student&school=4151010610", desktop],
  ["ui-list-a.png", "view=discover&variant=A", desktop],
  ["ui-list-b.png", "view=discover&variant=B", desktop],
  ["ui-list-c.png", "view=discover&variant=C", desktop],
  ["ui-list-mobile.png", "view=discover&variant=A", mobile],
  ["ui-item-detail.png", "view=item", desktop],
  ["ui-create-item.png", "view=create", desktop],
  ["ui-request-status.png", "view=request", desktop],
  ["ui-donation-form.png", "view=donate", desktop],
  ["ui-charity.png", "view=charity", desktop],
  ["ui-station-dashboard.png", "view=station", desktop],
  ["ui-admin-import.png", "view=admin", desktop],
  ["ui-login.png", "view=login&role=student&school=4151010610&campus=WANGJIANG", desktop],
  ["ui-register.png", "view=register&school=4151010610&campus=WANGJIANG", desktop],
  ["ui-login-station.png", "view=login&role=station", desktop],
  ["ui-login-platform.png", "view=login&role=admin", desktop],
  ["ui-login-university-admin.png", "view=login&role=university_admin", desktop],
];

const responsiveChecks = [
  ["discover", "view=discover&variant=A"],
  ["role", "view=role"],
  ["context", "view=context&role=student&school=4151010610"],
  ["item", "view=item"],
  ["admin", "view=admin"],
  ["login", "view=login&role=student&school=4151010610&campus=WANGJIANG"],
  ["create", "view=create"],
  ["charity", "view=charity"],
];

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForPort(profile, timeoutMs) {
  const file = path.join(profile, "DevToolsActivePort");
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (fs.existsSync(file)) {
      const [port] = fs.readFileSync(file, "utf8").trim().split(/\r?\n/);
      if (port) return Number(port);
    }
    await delay(100);
  }
  throw new Error("Edge DevTools endpoint did not start.");
}

async function connectCdp(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });
  return {
    send(method, params = {}) {
      const id = nextId++;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    },
    close() {
      socket.close();
    },
  };
}

async function evaluate(page, expression) {
  const result = await page.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result.value;
}

async function main() {
  fs.mkdirSync(ASSET_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(REPORT), { recursive: true });
  fs.mkdirSync(RESPONSIVE_DIR, { recursive: true });
  fs.mkdirSync(PROFILE, { recursive: true });

  const child = spawn(
    EDGE,
    [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--no-first-run",
      "--disable-background-networking",
      "--disable-component-update",
      "--allow-file-access-from-files",
      "--remote-debugging-port=0",
      `--user-data-dir=${PROFILE}`,
      "about:blank",
    ],
    { stdio: "ignore", windowsHide: true }
  );

  let page;
  const report = [];
  let interactionChecks = {};
  try {
    const port = await waitForPort(PROFILE, 12000);
    const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
      method: "PUT",
    }).then((response) => response.json());
    page = await connectCdp(target.webSocketDebuggerUrl);
    await page.send("Page.enable");
    await page.send("Runtime.enable");

    for (const [outputName, query, viewport] of targets) {
      await page.send("Emulation.setDeviceMetricsOverride", {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: viewport === mobile ? 1 : 1.25,
        mobile: false,
        screenWidth: viewport.width,
        screenHeight: viewport.height,
      });
      const url = `${pathToFileURL(PROTOTYPE).href}?${query}&capture=1`;
      await page.send("Page.navigate", { url });
      await delay(120);
      await evaluate(
        page,
        "document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))))"
      );
      const metrics = await page.send("Page.getLayoutMetrics");
      const content = metrics.cssContentSize;
      const pageAudit = await evaluate(
        page,
        `(() => {
          const nav = document.querySelector(".nav");
          return {
            viewport: innerWidth,
            overflow: document.documentElement.scrollWidth > innerWidth,
            h1: document.querySelectorAll("h1").length,
            main: document.querySelectorAll("main").length,
            nav_position: nav ? getComputedStyle(nav).position : "none",
            unlabeled_controls: [...document.querySelectorAll("input,select,textarea")]
              .filter((el) => !el.labels?.length && !el.getAttribute("aria-label") && !el.getAttribute("aria-labelledby")).length,
            small_targets: [...document.querySelectorAll("button,.nav a,.side-link,.btn,.campus-option,.filter-chip")]
              .filter((el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && (rect.width < 24 || rect.height < 24);
              }).length,
            text: document.body.innerText.slice(0, 120)
          };
        })()`
      );
      const shot = await page.send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
        captureBeyondViewport: true,
        clip: {
          x: 0,
          y: 0,
          width: viewport.width,
          height: Math.min(Math.ceil(content.height), 12000),
          scale: 1,
        },
      });
      fs.writeFileSync(path.join(ASSET_DIR, outputName), Buffer.from(shot.data, "base64"));
      report.push({
        output: outputName,
        query,
        viewport,
        content: { width: content.width, height: content.height },
        ...pageAudit,
      });

      const viewportShot = await page.send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
        captureBeyondViewport: false,
      });
      fs.writeFileSync(
        path.join(RESPONSIVE_DIR, `${path.parse(outputName).name}-viewport.png`),
        Buffer.from(viewportShot.data, "base64")
      );
    }

    for (const [name, query] of responsiveChecks) {
      for (const width of [375, 390, 768, 1024, 1440]) {
        const height = width < 600 ? 844 : 1000;
        await page.send("Emulation.setDeviceMetricsOverride", {
          width,
          height,
          deviceScaleFactor: 1,
          mobile: false,
          screenWidth: width,
          screenHeight: height,
        });
        const url = `${pathToFileURL(PROTOTYPE).href}?${query}&capture=1`;
        await page.send("Page.navigate", { url });
        await delay(120);
        await evaluate(
          page,
          "document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))))"
        );
        const audit = await evaluate(
          page,
          `(() => {
            const nav = document.querySelector(".nav");
            const navRect = nav ? nav.getBoundingClientRect() : null;
            return {
              viewport: innerWidth,
              overflow: document.documentElement.scrollWidth > innerWidth,
              h1: document.querySelectorAll("h1").length,
              main: document.querySelectorAll("main").length,
              nav_position: nav ? getComputedStyle(nav).position : "none",
              nav_bottom_gap: navRect ? Math.round(innerHeight - navRect.bottom) : null,
              nav_height: navRect ? Math.round(navRect.height) : null
            };
          })()`
        );
        const shot = await page.send("Page.captureScreenshot", {
          format: "png",
          fromSurface: true,
          captureBeyondViewport: false,
        });
        const shotPath = path.join(RESPONSIVE_DIR, `${name}-${width}.png`);
        fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
        report.push({ output: `${name}-${width}.png`, query, viewport: { width, height }, ...audit });
      }
    }

    await page.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
      screenWidth: 1440,
      screenHeight: 1000,
    });
    const contextUrl = `${pathToFileURL(PROTOTYPE).href}?view=context&role=student&school=4151010610&capture=1`;
    await page.send("Page.navigate", { url: contextUrl });
    await delay(150);
    const filteredSchools = await evaluate(
      page,
      `(() => {
        const input = document.querySelector("#school-search");
        input.value = "四川";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        const options = [...document.querySelectorAll("#school-options option")].map((option) => option.value);
        return {
          count: options.length,
          prefix_only: options.every((name) => name.startsWith("四川")),
          first: options.slice(0, 5)
        };
      })()`
    );
    await evaluate(
      page,
      `(() => {
        const input = document.querySelector("#school-search");
        input.value = "电子科技大学";
        input.dispatchEvent(new Event("change", { bubbles: true }));
      })()`
    );
    await delay(300);
    const selectedSchool = await evaluate(
      page,
      `({ search: location.search, heading: document.querySelector("h2")?.textContent || "" })`
    );

    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    await page.send("Page.navigate", { url: contextUrl });
    await delay(150);
    const reducedMotion = await evaluate(
      page,
      `({
        matches: matchMedia("(prefers-reduced-motion: reduce)").matches,
        duration: getComputedStyle(document.querySelector(".identity-option, .campus-option, .btn")).transitionDuration
      })`
    );
    await page.send("Page.navigate", { url: `${pathToFileURL(PROTOTYPE).href}?view=role&capture=1` });
    await delay(120);
    const roleFlow = await evaluate(
      page,
      `({
        options: [...document.querySelectorAll("#identity-select option")].map((option) => option.value),
        button: document.querySelector("#identity-form button")?.textContent || ""
      })`
    );
    await evaluate(
      page,
      `(() => {
        const select = document.querySelector("#identity-select");
        select.value = "station";
        select.dispatchEvent(new Event("change", { bubbles: true }));
        document.querySelector("#identity-form").requestSubmit();
      })()`
    );
    await delay(180);
    const roleDestination = await evaluate(page, "location.search");
    const authPrompts = {};
    for (const [role, query] of [
      ["student", "view=login&role=student&school=4151010610&campus=WANGJIANG"],
      ["station", "view=login&role=station"],
      ["admin", "view=login&role=admin"],
      ["university_admin", "view=login&role=university_admin"],
    ]) {
      await page.send("Page.navigate", { url: `${pathToFileURL(PROTOTYPE).href}?${query}&capture=1` });
      await delay(100);
      authPrompts[role] = await evaluate(page, "document.body.innerText.includes('前往注册')");
    }

    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "no-preference" }],
    });
    await page.send("Page.navigate", {
      url: `${pathToFileURL(PROTOTYPE).href}?view=discover&variant=A`,
    });
    await delay(380);
    const motion = await evaluate(
      page,
      `(() => {
        const items = [...document.querySelectorAll(".item-card")];
        items.at(-1)?.scrollIntoView({ block: "center" });
        return {
          enabled: document.body.classList.contains("motion-ready"),
          hero_animation: getComputedStyle(document.querySelector(".hero-copy h1")).animationName
        };
      })()`
    );
    await delay(420);
    motion.visible_items = await evaluate(page, "document.querySelectorAll('.item-card.is-visible').length");
    motion.total_items = await evaluate(
      page,
      `document.querySelectorAll(".item-card").length`
    );
    motion.last_visible = await evaluate(
      page,
      `document.querySelector(".item-card:last-child")?.classList.contains("is-visible") || false`
    );
    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    await page.send("Page.navigate", {
      url: `${pathToFileURL(PROTOTYPE).href}?view=discover&variant=A`,
    });
    await delay(180);
    motion.reduced_mode = await evaluate(
      page,
      `({
        active: matchMedia("(prefers-reduced-motion: reduce)").matches,
        motion_ready: document.body.classList.contains("motion-ready")
      })`
    );
    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "no-preference" }],
    });
    await page.send("Page.navigate", {
      url: `${pathToFileURL(PROTOTYPE).href}?view=discover&variant=A&school=4151010610`,
    });
    await delay(300);
    const schoolSceneCheck = await evaluate(
      page,
      `(async () => {
        const scene = document.querySelector("[data-school-scene]");
        const toggle = document.querySelector("[data-school-media-toggle]");
        const badge = toggle?.querySelector(".school-badge");
        if (!scene || !toggle || !badge) return { count: 0 };
        const before = scene.classList.contains("is-paused");
        toggle.click();
        await new Promise((resolve) => setTimeout(resolve, 50));
        const after = scene.classList.contains("is-paused");
        toggle.click();
        return {
          count: document.querySelectorAll("[data-school-scene]").length,
          hasSource: Boolean(scene.currentSrc || scene.src),
          badge_fills_control:
            Math.round(badge.getBoundingClientRect().width) === Math.round(toggle.getBoundingClientRect().width) &&
            Math.round(badge.getBoundingClientRect().height) === Math.round(toggle.getBoundingClientRect().height),
          toggle_label: toggle.getAttribute("aria-label"),
          toggle_size: [toggle.getBoundingClientRect().width, toggle.getBoundingClientRect().height],
          toggle_works: before !== after
        };
      })()`
    );
    const schoolBadges = [];
    for (const [name, school] of [
      ["scu", "4151010610"],
      ["swjtu", "4151010613"],
      ["uestc", "4151010614"],
      ["swufe", "4151010651"],
      ["sicau", "4151010626"],
    ]) {
      await page.send("Page.navigate", {
        url: `${pathToFileURL(PROTOTYPE).href}?view=discover&variant=A&school=${school}`,
      });
      await delay(180);
      const badge = await evaluate(
        page,
        `(() => {
          const toggle = document.querySelector("[data-school-media-toggle]");
          const image = toggle?.querySelector(".school-badge");
          if (!toggle || !image) return null;
          const toggleRect = toggle.getBoundingClientRect();
          const imageRect = image.getBoundingClientRect();
          return {
            source: image.currentSrc || image.src,
            fills_control:
              Math.round(toggleRect.width) === Math.round(imageRect.width) &&
              Math.round(toggleRect.height) === Math.round(imageRect.height),
            object_fit: getComputedStyle(image).objectFit
          };
        })()`
      );
      schoolBadges.push({ name, ...badge });
    }
    await page.send("Page.navigate", {
      url: `${pathToFileURL(PROTOTYPE).href}?view=charity`,
    });
    await delay(300);
    const charityVideoChecks = await evaluate(
      page,
      `(async () => {
        const videos = [...document.querySelectorAll("[data-video-player]")];
        const results = [];
        for (const video of videos) {
          const toggle = video.parentElement?.querySelector("[data-video-toggle]");
          video.pause();
          toggle?.click();
          await new Promise((resolve) => setTimeout(resolve, 80));
          const played = !video.paused;
          toggle?.click();
          await new Promise((resolve) => setTimeout(resolve, 60));
          results.push({
            hasSource: Boolean(video.currentSrc || video.querySelector("source")?.src),
            toggle_label: toggle?.getAttribute("aria-label") || "",
            toggle_size: toggle ? [toggle.getBoundingClientRect().width, toggle.getBoundingClientRect().height] : null,
            toggle_works: played && video.paused
          });
        }
        return { count: videos.length, items: results };
      })()`
    );
    interactionChecks = {
      school_search: filteredSchools,
      selected_school: selectedSchool,
      reduced_motion: reducedMotion,
      role_flow: roleFlow,
      role_destination: roleDestination,
      registration_visible: authPrompts,
      motion,
      school_scene: schoolSceneCheck,
      school_badges: schoolBadges,
      charity_videos: charityVideoChecks,
    };
  } finally {
    await page?.send("Browser.close").catch(() => {});
    page?.close();
    if (child.exitCode === null) child.kill();
  }

  const checkIssues = [];
  if (!interactionChecks.school_search?.prefix_only || interactionChecks.school_search.count === 0) {
    checkIssues.push("School search did not return prefix matches.");
  }
  if (!interactionChecks.selected_school?.search.includes("school=4151010614")) {
    checkIssues.push("Selecting a school did not update the context.");
  }
  if (!interactionChecks.reduced_motion?.matches) {
    checkIssues.push("Reduced-motion emulation did not activate.");
  }
  if (interactionChecks.role_flow?.options?.length !== 4) {
    checkIssues.push("Four login identities were not present.");
  }
  if (!interactionChecks.role_destination?.includes("view=login&role=station")) {
    checkIssues.push("Role dropdown did not route to the selected login.");
  }
  if (!interactionChecks.registration_visible?.student) {
    checkIssues.push("Student registration entry is missing.");
  }
  if (["station", "admin", "university_admin"].some((role) => interactionChecks.registration_visible?.[role])) {
    checkIssues.push("A non-student identity exposes registration.");
  }
  if (!interactionChecks.motion?.enabled || interactionChecks.motion?.hero_animation === "none") {
    checkIssues.push("Primary entrance motion did not initialize.");
  }
  if (!interactionChecks.motion?.visible_items || !interactionChecks.motion?.last_visible) {
    checkIssues.push("Item reveal motion did not expose cards after scrolling.");
  }
  if (!interactionChecks.motion?.reduced_mode?.active || interactionChecks.motion?.reduced_mode?.motion_ready) {
    checkIssues.push("Reduced motion did not suppress optional animation setup.");
  }
  const schoolScene = interactionChecks.school_scene;
  if (
    schoolScene?.count !== 1 ||
    !schoolScene?.hasSource ||
    !schoolScene?.badge_fills_control ||
    !schoolScene?.toggle_label ||
    !schoolScene?.toggle_works
  ) {
    checkIssues.push("The discover page school scene or its badge toggle is incomplete.");
  }
  if (!schoolScene?.toggle_size || schoolScene.toggle_size[0] < 44 || schoolScene.toggle_size[1] < 44) {
    checkIssues.push("The school scene toggle is smaller than 44 x 44.");
  }
  if (
    interactionChecks.school_badges?.length !== 5 ||
    interactionChecks.school_badges.some(
      (badge) => !badge?.source || !badge.fills_control || badge.object_fit !== "cover"
    )
  ) {
    checkIssues.push("One or more university badges do not fill their circular controls.");
  }
  if (
    interactionChecks.charity_videos?.count !== 2 ||
    interactionChecks.charity_videos.items.some(
      (video) => !video.hasSource || !video.toggle_label || !video.toggle_works || !video.toggle_size || video.toggle_size[0] < 44 || video.toggle_size[1] < 44
    )
  ) {
    checkIssues.push("The charity page videos or their accessible toggles are incomplete.");
  }
  fs.writeFileSync(
    REPORT,
    `${JSON.stringify({ renders: report, interaction: interactionChecks }, null, 2)}\n`,
    "utf8"
  );
  const failures = report.filter((item) => item.overflow || item.h1 !== 1 || item.main !== 1 || item.unlabeled_controls > 0 || item.small_targets > 0);
  console.log(JSON.stringify({ pages: report.length, failures, checkIssues, report: REPORT }, null, 2));
  if (failures.length || checkIssues.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
