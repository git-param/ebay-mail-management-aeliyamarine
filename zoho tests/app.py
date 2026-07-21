from flask import Flask, jsonify, request

from zoho_inventory import (
    search_inventory,
    serialize_item,
)


app = Flask(__name__)


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Zoho Inventory Search</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f5f7fb;
            color: #1f2937;
        }

        .page {
            max-width: 1500px;
            margin: 0 auto;
            padding: 28px;
        }

        .header {
            margin-bottom: 22px;
        }

        .header h1 {
            margin: 0 0 8px;
            font-size: 26px;
        }

        .header p {
            margin: 0;
            color: #64748b;
        }

        .search-panel {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 18px;
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
        }

        .search-panel input {
            flex: 1;
            height: 44px;
            padding: 0 14px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 15px;
            outline: none;
        }

        .search-panel input:focus {
            border-color: #2563eb;
        }

        .search-panel select {
            width: 110px;
            height: 44px;
            padding: 0 10px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            background: white;
        }

        .search-panel button {
            height: 44px;
            padding: 0 24px;
            border: none;
            border-radius: 8px;
            background: #2563eb;
            color: white;
            font-size: 15px;
            cursor: pointer;
        }

        .search-panel button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .status {
            min-height: 24px;
            margin: 0 0 12px;
            color: #475569;
        }

        .table-wrapper {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            overflow: auto;
        }

        table {
            width: 100%;
            min-width: 1250px;
            border-collapse: collapse;
        }

        th {
            background: #f8fafc;
            color: #475569;
            font-size: 12px;
            text-align: left;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            padding: 13px;
            border-bottom: 1px solid #e2e8f0;
            white-space: nowrap;
        }

        td {
            padding: 13px;
            border-bottom: 1px solid #e2e8f0;
            vertical-align: top;
            font-size: 14px;
        }

        tr:last-child td {
            border-bottom: none;
        }

        .product-cell {
            display: flex;
            min-width: 320px;
            gap: 12px;
            align-items: flex-start;
        }

        .product-image {
            width: 62px;
            height: 62px;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            object-fit: contain;
            background: #f8fafc;
            flex-shrink: 0;
        }

        .image-placeholder {
            width: 62px;
            height: 62px;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            background: #f1f5f9;
            color: #94a3b8;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            text-align: center;
            flex-shrink: 0;
        }

        .product-name {
            font-weight: 600;
            color: #1d4ed8;
            line-height: 1.45;
        }

        .product-brand {
            margin-top: 4px;
            color: #64748b;
            font-size: 12px;
        }

        .price {
            font-weight: 600;
            white-space: nowrap;
        }

        .description {
            max-width: 260px;
            white-space: normal;
            color: #475569;
            line-height: 1.45;
        }

        .empty {
            padding: 50px;
            text-align: center;
            color: #64748b;
        }

        .error {
            color: #dc2626;
        }

        @media (max-width: 700px) {
            .page {
                padding: 15px;
            }

            .search-panel {
                flex-direction: column;
            }

            .search-panel select,
            .search-panel button {
                width: 100%;
            }
        }

        .product-name {
            font-weight: 600;
            color: #1d4ed8;
            line-height: 1.45;
            text-decoration: none;
        }

        .product-name:hover {
            text-decoration: underline;
        }

    </style>
</head>

<body>
    <main class="page">
        <section class="header">
            <h1>Zoho Inventory Search</h1>

            <p>
                Search items by SKU, item name or part number.
            </p>
        </section>

        <section class="search-panel">
            <input
                id="keyword"
                type="text"
                placeholder="Enter SKU, name or part number"
                autocomplete="off"
            >

            <select id="limit">
                <option value="10">10 results</option>
                <option value="20" selected>20 results</option>
                <option value="50">50 results</option>
            </select>

            <button id="searchButton" type="button">
                Search
            </button>
        </section>

        <div id="status" class="status"></div>

        <section class="table-wrapper">
            <div id="emptyState" class="empty">
                Enter a keyword to search Zoho Inventory.
            </div>

            <table id="resultsTable" hidden>
                <thead>
                    <tr>
                        <th>Product</th>
                        <th>SKU</th>
                        <th>Part number</th>
                        <th>Condition</th>
                        <th>Stock</th>
                        <th>eBay USD</th>
                    </tr>
                </thead>

                <tbody id="resultsBody"></tbody>
            </table>
        </section>
    </main>

    <script>
        const keywordInput =
            document.getElementById("keyword");

        const limitSelect =
            document.getElementById("limit");

        const searchButton =
            document.getElementById("searchButton");

        const statusBox =
            document.getElementById("status");

        const resultsTable =
            document.getElementById("resultsTable");

        const resultsBody =
            document.getElementById("resultsBody");

        const emptyState =
            document.getElementById("emptyState");


        function escapeHtml(value) {
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }


        function formatPrice(value) {
            if (
                value === null ||
                value === undefined ||
                value === ""
            ) {
                return "—";
            }

            const text = String(value).trim();

            if (
                text.toUpperCase().startsWith("USD")
            ) {
                return text;
            }

            const numeric = Number(text);

            if (!Number.isNaN(numeric)) {
                return "USD " + numeric.toFixed(2);
            }

            return text;
        }


        function createImage(item) {
            if (!item.has_image || !item.image_url) {
                return `
                    <div class="image-placeholder">
                        No image
                    </div>
                `;
            }

            return `
                <img
                    class="product-image"
                    src="${escapeHtml(item.image_url)}"
                    alt="${escapeHtml(item.name)}"
                    loading="lazy"
                    onerror="
                        this.outerHTML =
                        '<div class=&quot;image-placeholder&quot;>No image</div>'
                    "
                >
            `;
        }


        function renderResults(items) {
            resultsBody.innerHTML = "";

            if (!items.length) {
                resultsTable.hidden = true;
                emptyState.hidden = false;
                emptyState.textContent =
                    "No matching inventory items found.";
                return;
            }

            emptyState.hidden = true;
            resultsTable.hidden = false;

            resultsBody.innerHTML = items.map((item) => `
                <tr>
                    <td>
                        <div class="product-cell">
                            <a
                                href="${escapeHtml(item.zoho_url)}"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                ${createImage(item)}
                            </a>

                            <div>
                                <a
                                    class="product-name"
                                    href="${escapeHtml(item.zoho_url)}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    ${escapeHtml(item.name)}
                                </a>

                                <div class="product-brand">
                                    ${escapeHtml(item.brand || "No brand")}
                                </div>
                            </div>
                        </div>
                    </td>

                    <td>${escapeHtml(item.sku || "—")}</td>

                    <td>
                        ${escapeHtml(item.part_number || "—")}
                    </td>

                    <td>
                        ${escapeHtml(item.condition || "—")}
                    </td>

                    <td>
                        ${escapeHtml(item.stock_on_hand ?? 0)}
                    </td>

                    <td class="price">
                        ${escapeHtml(formatPrice(item.ebay_price))}
                    </td>
                </tr>
            `).join("");
        }


        async function searchInventory() {
            const keyword = keywordInput.value.trim();
            const limit = limitSelect.value;

            if (!keyword) {
                statusBox.textContent =
                    "Please enter a search keyword.";

                keywordInput.focus();
                return;
            }

            searchButton.disabled = true;
            searchButton.textContent = "Searching...";

            statusBox.classList.remove("error");
            statusBox.textContent =
                `Searching for "${keyword}"...`;

            try {
                const response = await fetch(
                    `/api/search?q=${
                        encodeURIComponent(keyword)
                    }&limit=${
                        encodeURIComponent(limit)
                    }`
                );

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.error || "Search failed."
                    );
                }

                renderResults(data.items || []);

                statusBox.textContent =
                    `Found ${data.count} result(s) for "${keyword}".`;

            } catch (error) {
                resultsTable.hidden = true;
                emptyState.hidden = false;
                emptyState.textContent =
                    "Unable to load inventory results.";

                statusBox.classList.add("error");
                statusBox.textContent = error.message;

            } finally {
                searchButton.disabled = false;
                searchButton.textContent = "Search";
            }
        }


        searchButton.addEventListener(
            "click",
            searchInventory
        );

        keywordInput.addEventListener(
            "keydown",
            (event) => {
                if (event.key === "Enter") {
                    searchInventory();
                }
            }
        );
    </script>
</body>
</html>
"""


@app.get("/")
def index():
    return HTML_PAGE


@app.get("/api/search")
def search_api():
    keyword = request.args.get("q", "").strip()
    limit = request.args.get("limit", default=20, type=int)

    if not keyword:
        return jsonify({
            "error": "Search keyword is required.",
        }), 400

    limit = max(1, min(limit, 50))

    try:
        items = search_inventory(
            keyword=keyword,
            limit=limit,
        )

        results = [
            serialize_item(item)
            for item in items
        ]

        return jsonify({
            "keyword": keyword,
            "count": len(results),
            "items": results,
        })

    except Exception as error:
        return jsonify({
            "error": str(error),
        }), 500



if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )