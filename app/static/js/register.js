(() => {
  const form = document.getElementById("register-form");
  const sendButton = document.getElementById("send-sms-code");
  const captchaImage = document.getElementById("captcha-image");
  const captchaRefresh = document.getElementById("captcha-refresh");
  const captchaInput = document.getElementById("captcha");
  const smsInput = document.getElementById("sms_code");
  const verificationInput = form?.querySelector('input[name="verification_request_id"]');
  const status = document.getElementById("sms-request-status");

  if (!form || !sendButton || !captchaImage || !captchaRefresh || !captchaInput || !smsInput || !verificationInput || !status) {
    return;
  }

  let countdownTimer = null;

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("is-error", isError);
    status.hidden = !message;
  }

  function setMockCode(code) {
    let node = document.getElementById("mock-sms-code");
    if (!code) {
      node?.remove();
      return;
    }
    if (!node) {
      node = document.createElement("p");
      node.id = "mock-sms-code";
      node.className = "field-hint";
      status.insertAdjacentElement("afterend", node);
    }
    node.textContent = `本地模拟验证码：${code}`;
  }

  function startCountdown(epochSeconds) {
    window.clearInterval(countdownTimer);
    const tick = () => {
      const remaining = Math.max(0, Math.ceil(Number(epochSeconds) - Date.now() / 1000));
      sendButton.disabled = remaining > 0;
      sendButton.textContent = remaining > 0 ? `${remaining} 秒后重试` : "重新获取验证码";
      if (remaining === 0) window.clearInterval(countdownTimer);
    };
    tick();
    if (!sendButton.disabled) return;
    countdownTimer = window.setInterval(tick, 1000);
  }

  captchaRefresh.addEventListener("click", () => {
    const url = new URL(form.dataset.captchaUrl, window.location.origin);
    url.searchParams.set("t", String(Date.now()));
    captchaImage.src = url.toString();
    captchaInput.value = "";
    captchaInput.focus();
  });

  sendButton.addEventListener("click", async (event) => {
    if (!form.dataset.smsUrl) return;
    event.preventDefault();
    if (!form.reportValidity()) return;

    sendButton.disabled = true;
    setStatus("正在发送验证码…");
    try {
      const response = await fetch(form.dataset.smsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        body: new FormData(form),
      });
      const payload = await response.json();
      if (!response.ok) {
        const details = Object.values(payload.field_errors || {});
        throw new Error(details[0] || payload.message || "验证码发送失败，请稍后重试。");
      }

      verificationInput.value = payload.verification_token || "";
      captchaInput.required = false;
      captchaInput.value = "";
      setMockCode(payload.mock_code);
      setStatus(payload.message || "如果名单信息匹配，验证码将发送到预留手机号。");
      startCountdown(payload.resend_after);
      smsInput.focus();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "验证码发送失败，请稍后重试。", true);
      startCountdown(0);
    }
  });

  form.addEventListener("submit", () => {
    const submit = form.querySelector('button[type="submit"]:not(#send-sms-code)');
    if (!submit) return;
    submit.disabled = true;
    const label = submit.querySelector("span");
    if (label) label.textContent = "正在注册…";
  });

  startCountdown(form.dataset.resendAfter || 0);
})();
