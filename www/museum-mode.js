(function () {
  'use strict';

  const CLIENT_HEADER = 'X-Xiaohu-Client';
  const CLIENT_NAME = 'museum';
  const SESSION_STORAGE_KEY = 'xiaohu-museum-session-id';
  const IDLE_TIMEOUT_SECONDS = 180;
  const IDLE_WARNING_SECONDS = 30;
  const originalFetch = window.fetch.bind(window);

  let activeSessionId = '';
  let idleDeadline = 0;
  let idleTimer = 0;
  let resetInProgress = false;

  const apiPath = (input) => {
    const value = typeof input === 'string' ? input : input instanceof Request ? input.url : '';

    try {
      return new URL(value, window.location.origin).pathname;
    } catch (error) {
      return value;
    }
  };

  const requestMethod = (input, init) => {
    if (init && init.method) {
      return init.method.toUpperCase();
    }

    if (input instanceof Request) {
      return input.method.toUpperCase();
    }

    return 'GET';
  };

  const museumHeaders = (input, init) => {
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init && init.headers ? init.headers : undefined).forEach((value, key) => {
      headers.set(key, value);
    });
    headers.set(CLIENT_HEADER, CLIENT_NAME);
    return headers;
  };

  const emptySessionListResponse = () => new Response(
    JSON.stringify({ success: true, message: 'museum session list', data: [] }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );

  window.fetch = async (input, init = {}) => {
    const path = apiPath(input);
    const method = requestMethod(input, init);

    // 展陈屏不加载其他访客或普通网页的历史会话。
    if (path === '/api/sessions' && method === 'GET') {
      return emptySessionListResponse();
    }

    const nextInit = { ...init };

    if (path === '/api/session' && method === 'POST') {
      nextInit.headers = museumHeaders(input, init);
    }

    const response = await originalFetch(input, nextInit);

    if (path === '/api/session' && method === 'POST' && response.ok) {
      response.clone().json().then((payload) => {
        const sessionId = payload && payload.data && payload.data.session_id;

        if (sessionId) {
          activeSessionId = sessionId;
          window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
          resetIdleDeadline();
        }
      }).catch(() => {});
    }

    if (method === 'DELETE' && activeSessionId && path === `/api/session/${activeSessionId}`) {
      activeSessionId = '';
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    }

    return response;
  };

  const waitFor = (selector, timeoutMs = 15000) => new Promise((resolve, reject) => {
    const startedAt = Date.now();

    const poll = () => {
      const element = document.querySelector(selector);

      if (element) {
        resolve(element);
        return;
      }

      if (Date.now() - startedAt >= timeoutMs) {
        reject(new Error(`等待界面元素超时: ${selector}`));
        return;
      }

      window.setTimeout(poll, 100);
    };

    poll();
  });

  const deleteSession = async (sessionId) => {
    if (!sessionId) {
      return;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 3000);

    try {
      await originalFetch(`/api/session/${encodeURIComponent(sessionId)}`, {
        method: 'DELETE',
        headers: { [CLIENT_HEADER]: CLIENT_NAME },
        keepalive: true,
        signal: controller.signal,
      });
    } catch (error) {
      // 服务器的过期会话清理会处理断网或异常关机造成的残留。
    } finally {
      window.clearTimeout(timeout);
    }
  };

  const resetExperience = async () => {
    if (resetInProgress) {
      return;
    }

    resetInProgress = true;
    window.clearInterval(idleTimer);

    const recordButton = document.getElementById('recordBtn');
    if (recordButton && recordButton.classList.contains('recording')) {
      recordButton.click();
    }

    const sessionId = activeSessionId || window.localStorage.getItem(SESSION_STORAGE_KEY) || '';
    activeSessionId = '';
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    await deleteSession(sessionId);
    window.location.reload();
  };

  const updateIdleNotice = () => {
    if (!activeSessionId || !idleDeadline) {
      return;
    }

    const remainingSeconds = Math.max(0, Math.ceil((idleDeadline - Date.now()) / 1000));
    const notice = document.getElementById('museum-idle-notice');

    if (notice) {
      notice.textContent = `长时间未操作，${remainingSeconds} 秒后结束本次体验`;
      notice.classList.toggle('is-visible', remainingSeconds <= IDLE_WARNING_SECONDS);
    }

    if (remainingSeconds <= 0) {
      resetExperience();
    }
  };

  function resetIdleDeadline() {
    if (!activeSessionId) {
      return;
    }

    idleDeadline = Date.now() + IDLE_TIMEOUT_SECONDS * 1000;
    const notice = document.getElementById('museum-idle-notice');
    if (notice) {
      notice.classList.remove('is-visible');
    }

    if (!idleTimer) {
      idleTimer = window.setInterval(updateIdleNotice, 1000);
    }
  }

  const selectXiaoHuModel = async () => {
    const newChatButton = await waitFor('#welcomeNewChatBtn, #newChatBtn');
    newChatButton.click();

    await waitFor('.model-item');
    const xiaohuModel = Array.from(document.querySelectorAll('.model-item')).find((item) => (
      item.textContent && item.textContent.includes('小沪')
    ));

    if (!xiaohuModel) {
      throw new Error('没有找到小沪模型，请检查后端模型配置');
    }

    xiaohuModel.click();
    const confirmButton = await waitFor('#confirmBtn:not(:disabled)');
    confirmButton.click();
    await waitFor('#recordBtn');
  };

  const createStartScreen = () => {
    const screen = document.createElement('div');
    screen.id = 'museum-start-screen';
    screen.innerHTML = `
      <section class="museum-start-card" aria-labelledby="museum-start-title">
        <img class="museum-start-logo" src="/xiaohu-logo-day.png" alt="小沪" />
        <h1 id="museum-start-title">侬好，我是小沪</h1>
        <p>和我一道体验上海话、聊聊上海文化</p>
        <button id="museum-start-button" type="button">点击开始</button>
        <p class="museum-start-note">每位参观者使用独立的临时会话，结束后自动清除</p>
      </section>
    `;
    document.body.appendChild(screen);

    screen.querySelector('#museum-start-button').addEventListener('click', async () => {
      const startButton = screen.querySelector('#museum-start-button');
      startButton.disabled = true;
      startButton.textContent = '正在准备';

      try {
        await selectXiaoHuModel();
        screen.classList.add('is-hidden');
      } catch (error) {
        console.error(error);
        startButton.disabled = false;
        startButton.textContent = '再试一次';
      }
    });
  };

  const createControls = () => {
    const finishButton = document.createElement('button');
    finishButton.id = 'museum-finish-button';
    finishButton.type = 'button';
    finishButton.textContent = '结束本次体验';
    finishButton.addEventListener('click', resetExperience);
    document.body.appendChild(finishButton);

    const idleNotice = document.createElement('div');
    idleNotice.id = 'museum-idle-notice';
    idleNotice.setAttribute('role', 'status');
    document.body.appendChild(idleNotice);
  };

  const improveRecordButtonAccessibility = () => {
    const update = () => {
      const button = document.getElementById('recordBtn');
      if (!button) {
        return;
      }

      const label = button.disabled
        ? '小沪正在回答，请稍候'
        : button.classList.contains('recording')
          ? '停止说话并发送'
          : '开始说话';
      button.setAttribute('aria-label', label);
      button.title = label;
    };

    const observer = new MutationObserver(update);
    if (!document.body) {
      document.addEventListener('DOMContentLoaded', improveRecordButtonAccessibility, {
        once: true,
      });
      return;
    }

    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'disabled'],
    });
    update();
  };

  const initialize = () => {
    const staleSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY) || '';
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    deleteSession(staleSessionId);

    createStartScreen();
    createControls();
    improveRecordButtonAccessibility();

    ['pointerdown', 'touchstart'].forEach((eventName) => {
      document.addEventListener(eventName, resetIdleDeadline, { passive: true });
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
}());
