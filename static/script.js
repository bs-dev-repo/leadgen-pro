// LeadGen Pro - Shared Utilities

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function shortUrl(u) {
  return u.replace(/^https?:\/\/(www\.)?/, '').split('/')[0];
}

function formatDate(d) {
  return new Date(d).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric'
  });
}
