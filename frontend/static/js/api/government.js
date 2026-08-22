/**
 * Government / President / Parliament endpoints.
 *
 * A separate file from citizens.js because these are a different resource with a
 * different lifetime — the president page and the dashboard both read it, and
 * neither needs the citizen roster's pagination helpers.
 *
 * Same shape as the other API modules on purpose: a plain object literal declared
 * with `const`, loaded by a classic <script> tag, no exports and no build step.
 * Note it is a LEXICAL const, not a property of `window` — a page must include
 * this file before the page script that uses it, exactly like CitizensApi.
 *
 * READS ARE PUBLIC, WRITES PASS `auth: true`. That mirrors the backend, where
 * everything under GET is open to spectators and every mutation goes through
 * `require_admin`. Sending the token on a public GET would be harmless but
 * misleading, and it would make apiFetch redirect a logged-out spectator to the
 * login page just for looking at who the President is.
 */
const GovernmentApi = {
  /** The sitting government. Throws on a database that was never seeded (404). */
  async get() {
    return apiFetch("/api/v1/government");
  },

  /**
   * Every citizen eligible for office — living adults — annotated with what they
   * already hold. This is what the president page's picker renders.
   *
   * Resolves to { total, adult_age, items }. `adult_age` comes from the backend
   * so the page can explain who is missing and why without keeping its own copy
   * of the rule.
   */
  async candidates() {
    return apiFetch("/api/v1/government/candidates");
  },

  /** The chamber: { seats_total, seats_filled, seats_available, items }. */
  async parliament() {
    return apiFetch("/api/v1/government/parliament");
  },

  /**
   * Appoint or vacate offices, or set national policy.
   *
   * SEND ONLY WHAT YOU MEAN TO CHANGE. The backend reads this with
   * `exclude_unset`, so `{ president_citizen_id: 7 }` leaves the First Lady alone
   * while `{ president_citizen_id: null }` genuinely vacates the presidency.
   * Passing an object with every key set to null would empty the whole
   * government — which is why the helpers below build minimal payloads.
   */
  async update(fields) {
    return apiFetch("/api/v1/government", {
      method: "PATCH",
      auth: true,
      body: JSON.stringify(fields),
    });
  },

  /** Appoint a President. `citizenId` of null vacates the office. */
  async setPresident(citizenId) {
    return GovernmentApi.update({ president_citizen_id: citizenId });
  },

  /** Appoint a First Lady. `citizenId` of null vacates the office. */
  async setFirstLady(citizenId) {
    return GovernmentApi.update({ first_lady_citizen_id: citizenId });
  },

  /** Fill any VACANT office automatically, leaving filled ones alone. */
  async autoAppoint() {
    return apiFetch("/api/v1/government/auto-appoint", {
      method: "POST",
      auth: true,
    });
  },

  /**
   * Seat a citizen in parliament. Omit `seatNumber` for the lowest free seat,
   * which is the normal case.
   */
  async appointMp(citizenId, party = null, seatNumber = null) {
    const body = { citizen_id: citizenId };
    if (party) body.party = party;
    if (seatNumber) body.seat_number = seatNumber;
    return apiFetch("/api/v1/government/parliament", {
      method: "POST",
      auth: true,
      body: JSON.stringify(body),
    });
  },

  /** `memberId` is the SEAT RECORD id, not the citizen id. */
  async updateMp(memberId, fields) {
    return apiFetch(`/api/v1/government/parliament/${memberId}`, {
      method: "PATCH",
      auth: true,
      body: JSON.stringify(fields),
    });
  },

  /** Vacate a seat. The citizen is untouched — this is neither death nor delete. */
  async removeMp(memberId) {
    return apiFetch(`/api/v1/government/parliament/${memberId}`, {
      method: "DELETE",
      auth: true,
    });
  },
};
