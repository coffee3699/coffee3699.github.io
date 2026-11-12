(() => {
  const browser = document.querySelector('.article-browser');
  if (!browser) return;
  const links = [...browser.querySelectorAll('[data-topic]')];
  const posts = [...browser.querySelectorAll('[data-post-tags]')];
  const status = browser.querySelector('.filter-status');
  const empty = browser.querySelector('.filter-empty');
  function filter(topic) {
    let count = 0;
    posts.forEach(post => {
      const tags = JSON.parse(post.dataset.postTags);
      post.hidden = Boolean(topic) && !tags.includes(topic);
      if (!post.hidden) count++;
    });
    links.forEach(link => {
      const active = link.dataset.topic === topic;
      link.classList.toggle('is-active', active);
      if (active) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
    status.textContent = topic ? `${topic} · ${count} 篇文章` : `共 ${count} 篇文章`;
    empty.hidden = count > 0;
    empty.textContent = topic ? '该标签下暂无文章，点击「全部」查看其他文章。' : '暂无文章。';
  }
  links.forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const url = new URL(window.location.href);
    const topic = link.dataset.topic;
    if (topic) url.searchParams.set('tag', topic);
    else url.searchParams.delete('tag');
    window.history.pushState(null, '', url);
    filter(topic);
  }));
  const restore = () => filter(new URL(window.location.href).searchParams.get('tag') || '');
  window.addEventListener('popstate', restore);
  restore();
})();
