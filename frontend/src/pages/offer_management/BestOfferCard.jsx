import { useState } from "react";
import {
  bestOfferPrices,
  bestOfferMoney,
  bestOfferDate,
  bestOfferStatusKey,
  bestOfferStatusLabel,
  bestOfferStatusGroup,
  bestOfferGroupLabels,
} from "./bestOfferFormat";
import { ebayMarketplaceHost, ebayListingUrl } from "../../utils/ebayUrls";
import OfferThumbnail from "./OfferThumbnail";

export default function BestOfferCard({
  offer,
  now,
  onAction,
  onDone,
  doneBusy,
  loading,
}) {
  const [selectedSide, setSelectedSide] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const listing = offer.listing || {};
  const listingUrl = ebayListingUrl(
    offer.listing_id,
    ebayMarketplaceHost({
      account_name: offer.account_name,
      ebay_username: offer.account_username,
    }),
  );
  const remaining = offer.expires_at
    ? Math.max(0, new Date(offer.expires_at).getTime() - now)
    : null;
  const status = bestOfferStatusKey(
    offer.provider_status || offer.status || offer.display_status,
  );
  const group = offer.status_group || bestOfferStatusGroup(status);
  const closed = ["COMPLETED", "CLOSED"].includes(group);
  const steps = offer.negotiation || [];
  const latestBuyer = [...steps]
    .reverse()
    .find((step) => step.side === "buyer");
  const latestSeller = [...steps]
    .reverse()
    .find((step) => step.side === "seller");
  const canSwitch = !closed && Boolean(latestBuyer && latestSeller);
  const side = canSwitch
    ? selectedSide || offer.latest_side || "buyer"
    : offer.latest_side;
  const selectedStep =
    !closed &&
    (side === "buyer" ? latestBuyer : side === "seller" ? latestSeller : null);
  const prices = bestOfferPrices(
    selectedStep
      ? {
          ...offer,
          amount: selectedStep.amount,
          currency: selectedStep.currency,
        }
      : offer,
  );
  const shownHistory =
    closed || !side
      ? [...steps].reverse()
      : [...steps].reverse().filter((step) => step.side === side);
  const roleLabel =
    offer.provider_role === "Seller"
      ? "Your account is selling"
      : offer.provider_role === "Buyer"
        ? "Your account is buying"
        : "Historical record - account role unavailable";
  const countdown = closed
    ? group === "COMPLETED"
      ? offer.status_verified && offer.provider_status
        ? "Accepted - payment completed"
        : "Accepted offer - closed"
      : "Offer closed"
    : group === "AGREED"
      ? bestOfferStatusLabel(status): group === "UNKNOWN" ? "Provider status awaiting review": remaining == null? "-": remaining === 0? "Offer deadline passed - checking its status": `${Math.floor(remaining / 3600000)}h ${Math.floor(remaining / 60000) % 60}m ${Math.floor(remaining / 1000) % 60}s`;
  const canRespond =!loading &&offer.can_respond &&remaining > 0 && (!canSwitch || side === offer.latest_side);

  return (
    <article
      className={`best-offer-card ${canSwitch ? "bo-has-side-switch" : ""}`}
    >
      {canSwitch ? (
        <button
          className="bo-side-switch"
          type="button"
          aria-label={`Show ${side === "buyer" ? "seller" : "buyer"} side offer`}
          title="Switch buyer and seller offers"
          onClick={() => {
            setSelectedSide(side === "buyer" ? "seller" : "buyer");
            setShowHistory(false);
          }}
        >
          <span aria-hidden="true">↔</span>{" "}
          {side === "buyer" ? "Buyer side" : "Seller side"}
        </button>
      ) : null}
      <OfferThumbnail
        key={offer.listing_id}
        listing={listing}
        href={listingUrl}
      />
      <div className="best-offer-product">
        <div className="bo-card-badges">
          <span
            className={`best-offer-status bo-status-${status.toLowerCase()} bo-group-${group.toLowerCase()}`}
          >
            {offer.display_status || bestOfferStatusLabel(status)}
          </span>
          <span className="bo-lifecycle-label">
            {bestOfferGroupLabels[group]}
          </span>
          <span className="bo-offer-role">{roleLabel}</span>
        </div>
        {!offer.status_verified ? (
          <small className="bo-history-label">
            Saved from earlier records; current eBay status has not been
            confirmed
          </small>
        ) : null}
        <h2>
          {listingUrl ? (
            <a
              className="bo-product-link"
              href={listingUrl}
              target="_blank"
              rel="noreferrer"
            >
              {listing.title || `Item ${offer.listing_id}`}{" "}
              <span aria-hidden="true">↗</span>
            </a>
          ) : (
            listing.title || "Unknown item"
          )}
        </h2>
        <dl className="bo-card-details">
          <div>
            <dt>Synced account</dt>
            <dd>{offer.account_name || "-"}</dd>
          </div>
          {selectedStep ? (
            <div>
              <dt>Viewing</dt>
              <dd>{side === "buyer" ? "Buyer offer" : "Seller offer"}</dd>
            </div>
          ) : offer.offer_from || offer.offer_to ? (
            <div>
              <dt>Offer direction</dt>
              <dd>
                {offer.offer_from || "Unknown"} → {offer.offer_to || "Unknown"}
              </dd>
            </div>
          ) : null}
          <div>
            <dt>Buyer</dt>
            <dd>{offer.buyer || "-"}</dd>
          </div>
          <div>
            <dt>Item ID</dt>
            <dd>
              {listingUrl ? (
                <a href={listingUrl} target="_blank" rel="noreferrer">
                  {offer.listing_id}
                </a>
              ) : (
                "-"
              )}
            </dd>
          </div>
          <div>
            <dt>Offer ID</dt>
            <dd>{selectedStep?.offer_id || offer.provider_offer_id || "-"}</dd>
          </div>
          <div>
            <dt>SKU</dt>
            <dd>{listing.sku || "-"}</dd>
          </div>
          <div>
            <dt>Condition</dt>
            <dd>{listing.condition || "-"}</dd>
          </div>
          {offer.seller ? (
            <div>
              <dt>Seller</dt>
              <dd>{offer.seller}</dd>
            </div>
          ) : null}
        </dl>
        {selectedStep?.message || (!selectedStep && offer.buyer_message) ? (
          <blockquote>
            {selectedStep?.message || offer.buyer_message}
          </blockquote>
        ) : null}
        <div className="bo-card-dates">
          <span>
            {selectedStep?.at
              ? `Offer made: ${bestOfferDate(selectedStep.at)}`
              : offer.received_at || offer.created_at_provider
                ? `Received by eBay: ${bestOfferDate(offer.received_at || offer.created_at_provider)}`
                : `Added to ACES: ${bestOfferDate(offer.first_seen_at)}`}
          </span>
          <span>
            {offer.status_verified
              ? "Last checked with eBay"
              : "Last processed in ACES"}
            : {bestOfferDate(offer.last_synced_at)}
          </span>
        </div>
      </div>
      <div className="best-offer-prices">
        <div className="bo-price-heading">
          <span>
            {selectedStep
              ? `${side === "buyer" ? "Buyer" : "Seller"} offer`
              : "Offer amount"}
          </span>
          {prices.currency ? (
            <span className="bo-currency">{prices.currency}</span>
          ) : null}
        </div>
        <strong>{prices.amount}</strong>
        <span>Listing price</span>
        <b>{prices.listingPrice}</b>
        {prices.listingNote ? (
          <small className="bo-price-note">{prices.listingNote}</small>
        ) : null}
        <span className="bo-quantity">
          Quantity: <b>{selectedStep?.quantity || offer.quantity || "-"}</b>
        </span>
        <time title={bestOfferDate(offer.expires_at)}>{countdown}</time>
        {offer.last_action ? (
          <p className="best-offer-action-state">
            {offer.last_action.action}:{" "}
            {offer.last_action.state === "SUCCEEDED"
              ? "Confirmed by eBay; provider state awaits synchronization"
              : offer.last_action.state}
          </p>
        ) : null}
        {offer.reconciliation_required ? (
          <small>Checking for a recent status change</small>
        ) : null}
      </div>
      <div className="bo-card-footer">
        {steps.length ? (
          <button
            className="bo-show-history"
            type="button"
            aria-expanded={showHistory}
            onClick={() => setShowHistory((value) => !value)}
          >
            {showHistory ? "Hide history" : "> Show history"}
          </button>
        ) : null}
        {canRespond ? (
          <div className="best-offer-actions">
            <button
              className="primary-button"
              onClick={() => onAction(offer, "Accept")}
            >
              Accept
            </button>
            <button
              className="secondary-button"
              onClick={() => onAction(offer, "Counter")}
            >
              Counter Offer
            </button>
            <button
              className="secondary-button"
              onClick={() => onAction(offer, "Decline")}
            >
              Decline
            </button>
          </div>
        ) : null}
        {onDone ? (
          <button
            className="secondary-button bo-done-button"
            type="button"
            disabled={loading || doneBusy}
            onClick={() => onDone(offer)}
          >
            {doneBusy ? "Saving..." : "Mark as done"}
          </button>
        ) : null}
        {offer.done_at ? (
          <small>Marked done: {bestOfferDate(offer.done_at)}</small>
        ) : null}
        {listingUrl ? (
          <a
            className="bo-ebay-link"
            href={listingUrl}
            target="_blank"
            rel="noreferrer"
          >
            View on eBay
          </a>
        ) : null}
      </div>
      {showHistory && steps.length ? (
        <div className="bo-negotiation-history">
          <strong>
            {closed || !side
              ? "Buyer and seller history"
              : side === "seller"
                ? "Seller history"
                : "Buyer history"}
          </strong>
          <ol>
            {shownHistory.map((step) => (
              <li key={step.id}>
                <span className="bo-history-side">
                  {step.side === "seller"
                    ? "Seller"
                    : step.side === "buyer"
                      ? "Buyer"
                      : "Offer"}
                </span>
                <b>{bestOfferMoney(step.amount, step.currency)}</b>
                <time>{bestOfferDate(step.at)}</time>
              </li>
            ))}
          </ol>
          {!shownHistory.length ? (
            <p>No offers recorded for this side.</p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
