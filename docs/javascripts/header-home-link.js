document$.subscribe(() => {
  const logoLink = document.querySelector('.md-logo');
  const topicEllipsis = document.querySelector('.md-header__title .md-header__topic:first-child .md-ellipsis');

  if (!logoLink || !topicEllipsis) {
    return;
  }

  if (topicEllipsis.closest('a.pkg-home-link')) {
    return;
  }

  const anchor = document.createElement('a');
  anchor.className = 'pkg-home-link';
  anchor.href = logoLink.getAttribute('href') || '.';
  anchor.textContent = topicEllipsis.textContent || 'nbdctools';

  topicEllipsis.replaceWith(anchor);
});
