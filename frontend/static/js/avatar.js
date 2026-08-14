/**
 * Every citizen gets a deterministic illustrated avatar (seeded by their
 * id, so it's stable across reloads) via DiceBear's public avatar API —
 * illustrated "persona" style, not photorealistic, which is the right
 * choice for procedurally-generated fictional citizens. Wrapped in a
 * colored ring that reflects current_activity, so the avatar doubles as
 * a live status indicator — see custom.css's .avatar-ring rules.
 */
const AsimAvatar = (() => {
  const STYLE = "notionists";

  function url(seed, size = 64) {
    return `https://api.dicebear.com/10.x/${STYLE}/svg?seed=${encodeURIComponent(seed)}&size=${size}&backgroundType=gradientLinear&backgroundColor=b6c7ff,e5d4ff,c7f5e8`;
  }

  function statusClass(activity) {
    const known = ["working", "socializing", "sleeping", "idle", "posting", "eating"];
    return known.includes(activity) ? activity : "idle";
  }

  /**
   * @param {number|string} seed - stable identity (citizen id)
   * @param {string} activity - current_activity, drives the ring color
   * @param {number} size - pixel diameter
   */
  function ringedImg(seed, activity, size = 64) {
    const cls = statusClass(activity);
    return `
      <span class="avatar-ring status-${cls}" style="width:${size + 5}px; height:${size + 5}px;">
        <img class="avatar" src="${url(seed, size)}" width="${size}" height="${size}" alt="" loading="lazy" />
      </span>`;
  }

  /** Plain avatar, no status ring — for contexts without a live activity (e.g. a comment author). */
  function plainImg(seed, size = 40) {
    return `<img class="avatar" src="${url(seed, size)}" width="${size}" height="${size}" alt="" loading="lazy" />`;
  }

  return { url, ringedImg, plainImg };
})();
