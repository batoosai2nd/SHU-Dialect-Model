(function () {
  const shell = document.getElementById('live2d-shell');
  const frame = document.getElementById('live2d-frame');
  const bubble = document.createElement('div');
  const bubbleContent = document.createElement('p');

  bubble.id = 'live2d-bubble';
  bubble.setAttribute('aria-hidden', 'true');
  bubbleContent.className = 'live2d-bubble__content';
  bubble.appendChild(bubbleContent);

  if (!shell || !(frame instanceof HTMLIFrameElement)) {
    return;
  }

  shell.appendChild(bubble);

  let frameReady = false;
  let isWidgetVisible = false;
  let stateResetTimer = 0;
  let bubbleHideTimer = 0;
  let activationId = 0;
  let defaultScheduledForActivation = -1;
  let lastLoadingTriggerAt = 0;
  let lastSpeakingTriggerAt = 0;
  let lastEndedTriggerAt = 0;
  let lastBubbleIndex = -1;
  let lastBubbleTriggerAt = 0;
  let iframeInteractionBridgeBound = false;

  const phrases = [
    '早浪相好~',
    '宗浪向好~',
    '下半日好~',
    '夜里相好~',
    '侬好，碰到侬交关开心！',
    '侬最近好伐？',
    '长远勿见，我老想念侬额！',
    '上海大学欢迎侬！',
    '我是上海大学的小沪',
    '侬想聊啥，阿拉一道聊聊看！',
    '阿拉上海闲话交关有腔调',
  ];

  const isXiaoHuActive = () => Boolean(document.querySelector('.container.theme-xiaohu'));

  const clearStateResetTimer = () => {
    if (stateResetTimer) {
      window.clearTimeout(stateResetTimer);
      stateResetTimer = 0;
    }
  };

  const hideBubble = () => {
    if (bubbleHideTimer) {
      window.clearTimeout(bubbleHideTimer);
      bubbleHideTimer = 0;
    }

    bubble.classList.remove('is-visible');
    bubble.setAttribute('aria-hidden', 'true');
  };

  const pickPhrase = () => {
    if (phrases.length === 0) {
      return '';
    }

    if (phrases.length === 1) {
      lastBubbleIndex = 0;
      return phrases[0];
    }

    let nextIndex = Math.floor(Math.random() * phrases.length);

    if (nextIndex === lastBubbleIndex) {
      nextIndex = (nextIndex + 1) % phrases.length;
    }

    lastBubbleIndex = nextIndex;
    return phrases[nextIndex];
  };

  const showBubble = (text) => {
    if (!text || !isXiaoHuActive()) {
      return;
    }

    if (bubbleHideTimer) {
      window.clearTimeout(bubbleHideTimer);
    }

    bubbleContent.textContent = text;
    bubble.classList.add('is-visible');
    bubble.setAttribute('aria-hidden', 'false');

    bubbleHideTimer = window.setTimeout(() => {
      hideBubble();
    }, 3200);
  };

  const triggerBubble = () => {
    const now = Date.now();

    if (now - lastBubbleTriggerAt < 220) {
      return;
    }

    lastBubbleTriggerAt = now;
    showBubble(pickPhrase());
  };

  const getWidgetApi = () => {
    if (!frameReady || !frame.contentWindow) {
      return null;
    }

    try {
      return frame.contentWindow.xiaohuLive2D || null;
    } catch (error) {
      return null;
    }
  };

  const invokeWidget = (action, token = activationId, retries = 30) => {
    const attempt = (remaining) => {
      if (token !== activationId || !isXiaoHuActive()) {
        return;
      }

      const api = getWidgetApi();

      if (api) {
        Promise.resolve(action(api)).catch(() => {});
        return;
      }

      if (remaining <= 0) {
        return;
      }

      window.setTimeout(() => attempt(remaining - 1), 120);
    };

    attempt(retries);
  };

  const setDefaultState = (delay = 0) => {
    if (!isXiaoHuActive()) {
      return;
    }

    clearStateResetTimer();
    const token = activationId;

    if (defaultScheduledForActivation === token) {
      return;
    }

    defaultScheduledForActivation = token;

    window.setTimeout(() => {
      invokeWidget((api) => api.setDefaultState(), token);
    }, delay);
  };

  const setState = (state, fallbackDelay = 0) => {
    if (!isXiaoHuActive()) {
      return;
    }

    clearStateResetTimer();
    defaultScheduledForActivation = -1;
    const token = activationId;

    invokeWidget((api) => {
      if (typeof api.getState === 'function' && api.getState() === state) {
        return true;
      }

      return api.setState(state);
    }, token);

    if (fallbackDelay > 0) {
      stateResetTimer = window.setTimeout(() => {
        setDefaultState();
      }, fallbackDelay);
    }
  };

  const updateVisibility = () => {
    const shouldShowWidget = isXiaoHuActive();

    shell.classList.toggle('is-active', shouldShowWidget);
    shell.setAttribute('aria-hidden', shouldShowWidget ? 'false' : 'true');

    if (shouldShowWidget && !isWidgetVisible) {
      activationId += 1;
      defaultScheduledForActivation = -1;

      if (frameReady) {
        setDefaultState(180);
      }
    }

    if (!shouldShowWidget) {
      clearStateResetTimer();
      defaultScheduledForActivation = -1;
      hideBubble();
    }

    isWidgetVisible = shouldShowWidget;
  };

  const observer = new MutationObserver(updateVisibility);

  const isSendButton = (button) => {
    const label = `${button.innerText || ''} ${button.getAttribute('aria-label') || ''}`.trim();
    return /\u53d1\u9001|send/i.test(label);
  };

  const handleClick = (event) => {
    if (!isXiaoHuActive()) {
      return;
    }

    const button = event.target instanceof Element ? event.target.closest('button') : null;

    if (button && isSendButton(button)) {
      triggerLoading();
    }
  };

  const triggerLoading = () => {
    const now = Date.now();

    if (now - lastLoadingTriggerAt < 350) {
      return;
    }

    lastLoadingTriggerAt = now;
    setState('loading', 10000);
  };

  const handleKeydown = (event) => {
    if (!isXiaoHuActive() || event.key !== 'Enter' || event.shiftKey) {
      return;
    }

    const target = event.target;
    const canSubmitFromKeyboard =
      target instanceof HTMLTextAreaElement ||
      (target instanceof HTMLInputElement && target.type !== 'button' && target.type !== 'submit');

    if (canSubmitFromKeyboard && String(target.value || '').trim()) {
      triggerLoading();
    }
  };

  const handleSubmit = () => {
    if (!isXiaoHuActive()) {
      return;
    }

    triggerLoading();
  };

  const handleAudioPlay = (event) => {
    if (!isXiaoHuActive() || !(event.target instanceof HTMLAudioElement)) {
      return;
    }

    const now = Date.now();

    if (now - lastSpeakingTriggerAt < 250) {
      return;
    }

    lastSpeakingTriggerAt = now;
    setState('speaking');
  };

  const handleAudioEnded = (event) => {
    if (!isXiaoHuActive() || !(event.target instanceof HTMLAudioElement)) {
      return;
    }

    const now = Date.now();

    if (now - lastEndedTriggerAt < 250) {
      return;
    }

    lastEndedTriggerAt = now;
    setState('yes', 1500);
  };

  const handleWidgetMessage = (event) => {
    if (event.origin !== window.location.origin || event.source !== frame.contentWindow) {
      return;
    }

    if (!isXiaoHuActive() || !event.data || event.data.type !== 'xiaohu-live2d:avatar-tap') {
      return;
    }

    triggerBubble();
  };

  const bindIframeInteractionBridge = () => {
    if (iframeInteractionBridgeBound || !frame.contentWindow) {
      return;
    }

    try {
      const iframeDocument = frame.contentWindow.document;

      if (!iframeDocument) {
        return;
      }

      iframeDocument.addEventListener('pointerup', () => {
        if (!isXiaoHuActive()) {
          return;
        }

        triggerBubble();
      }, true);

      iframeInteractionBridgeBound = true;
    } catch (error) {
      iframeInteractionBridgeBound = false;
    }
  };

  const startObserver = () => {
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class'],
    });

    frame.addEventListener('load', () => {
      frameReady = true;
      iframeInteractionBridgeBound = false;
      defaultScheduledForActivation = -1;
      bindIframeInteractionBridge();

      if (isXiaoHuActive()) {
        setDefaultState(240);
      }
    });

    document.addEventListener('click', handleClick, true);
    document.addEventListener('keydown', handleKeydown, true);
    document.addEventListener('submit', handleSubmit, true);
    document.addEventListener('play', handleAudioPlay, true);
    document.addEventListener('ended', handleAudioEnded, true);
    window.addEventListener('message', handleWidgetMessage);

    updateVisibility();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startObserver, { once: true });
  } else {
    startObserver();
  }
})();
