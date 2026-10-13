const tocLinks = [...document.querySelectorAll('.detail-toc a[href^="#"], .help-toc a[href^="#"]')];
const sections = tocLinks
  .map((link) => document.getElementById(link.hash.slice(1)))
  .filter(Boolean);

const selectSection = (section) => {
  tocLinks.forEach((link) => {
    const active = link.hash === `#${section.id}`;
    link.classList.toggle("toc-current", active);
    if (active) {
      link.setAttribute("aria-current", "location");
    } else {
      link.removeAttribute("aria-current");
    }
  });
};

if (sections.length) {
  selectSection(sections[0]);
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top);
      if (visible.length) selectSection(visible[0].target);
    },
    { rootMargin: "-15% 0px -70% 0px", threshold: 0 },
  );
  sections.forEach((section) => observer.observe(section));
}
