// Shared sidebar shell for JobCraft mockups. Each page has <div id="sidebar"></div>;
// this injects the nav and marks the active link from the page's data-page attribute.
// In Next.js this becomes a <Sidebar> layout component.
(function () {
  const NAV = [
    { page: 'dashboard',    href: 'dashboard.html',    label: 'Dashboard',
      icon: '<path d="M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z"/>' },
    { page: 'jobs',         href: 'jobs.html',         label: 'Jobs',
      icon: '<path d="M20 7h-4V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2Zm-6 0h-4V5h4v2Z"/>' },
    { page: 'apply-queue',  href: 'apply-queue.html',  label: 'Apply Queue', badge: 'queue',
      icon: '<path d="m9 16.2-3.5-3.5L4 14.2 9 19l11-11-1.4-1.4z"/>' },
    { page: 'applications', href: 'applications.html', label: 'Applications',
      icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm2 16H8v-2h8v2Zm0-4H8v-2h8v2Zm-3-5V3.5L18.5 9H13Z"/>' },
    { page: 'documents',    href: 'documents.html',    label: 'Documents',
      icon: '<path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6H6Zm7 1.5L18.5 9H13V3.5ZM8 13h8v1.5H8V13Zm0 3h8v1.5H8V16Z"/>' },
    { page: 'experience',   href: 'experience.html',   label: 'Experience',
      icon: '<path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5Zm0 2c-3.3 0-10 1.7-10 5v3h20v-3c0-3.3-6.7-5-10-5Z"/>' },
    { page: 'settings',     href: 'settings.html',     label: 'Settings',
      icon: '<path d="M19.4 13a7.8 7.8 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-1.7-1l-.4-2.6H10.1l-.4 2.6a7.6 7.6 0 0 0-1.7 1l-2.4-1-2 3.4L3.6 11a7.8 7.8 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 1.7 1l.4 2.6h3.8l.4-2.6a7.6 7.6 0 0 0 1.7-1l2.4 1 2-3.4L19.4 13ZM12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5Z"/>' },
    { divider: 'Observability' },
    { page: 'admin-calls',   href: 'admin-calls.html',   label: 'LLM Calls',
      icon: '<path d="M3 5h18v2H3V5Zm0 6h18v2H3v-2Zm0 6h12v2H3v-2Z"/>' },
    { page: 'admin-evals',   href: 'admin-evals.html',   label: 'Evals',
      icon: '<path d="M3 3h2v18H3V3Zm4 10h3v8H7v-8Zm5-6h3v14h-3V7Zm5 3h3v11h-3V10Z"/>' },
    { page: 'admin-prompts', href: 'admin-prompts.html', label: 'Prompts',
      icon: '<path d="M4 4h16v2H4V4Zm0 5h10v2H4V9Zm0 5h16v2H4v-2Zm0 5h10v2H4v-2Z"/>' },
  ];

  const active = document.body.getAttribute('data-page');
  const links = NAV.map((n) => {
    if (n.divider) {
      return `<div class="px-3 pt-4 pb-1 text-[0.65rem] font-semibold uppercase tracking-wide text-zinc-400">${n.divider}</div>`;
    }
    const badge = n.badge === 'queue'
      ? '<span class="num ml-auto text-xs bg-amber-100 text-amber-700 rounded-full px-1.5">12</span>'
      : '';
    return `<a href="${n.href}" class="nav-link ${n.page === active ? 'active' : ''}">
      <svg viewBox="0 0 24 24" fill="currentColor">${n.icon}</svg>
      <span>${n.label}</span>${badge}
    </a>`;
  }).join('');

  document.getElementById('sidebar').innerHTML = `
    <div class="h-full flex flex-col">
      <div class="px-3 py-4 flex items-center gap-2.5 border-b border-zinc-200">
        <div class="w-8 h-8 rounded-lg bg-brand-600 text-white grid place-items-center shadow-sm" style="box-shadow:0 1px 2px rgba(79,70,229,.35)">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>
        </div>
        <div>
          <div class="font-semibold text-sm leading-tight tracking-tight">JobCraft</div>
          <div class="text-[0.7rem] text-zinc-400 leading-tight tracking-wide uppercase">SG · job hunt</div>
        </div>
      </div>
      <nav class="flex-1 p-2 space-y-0.5">${links}</nav>
      <div class="p-3 border-t border-zinc-200 flex items-center gap-2">
        <div class="w-7 h-7 rounded-full bg-zinc-200 grid place-items-center text-xs font-semibold text-zinc-600">BO</div>
        <div class="text-xs"><div class="font-medium text-zinc-700">Bruce Ong</div>
          <div class="text-zinc-400">Autopilot: <span class="text-emerald-600 font-medium">selective</span></div></div>
      </div>
    </div>`;
})();
