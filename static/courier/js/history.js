// Halaman Riwayat Pikap: filter status, nomor halaman, dan unduh CSV.
(function () {
    var PER_PAGE = 8;

    var table = document.getElementById("hist-table");
    if (!table) return;

    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-status]"));
    var emptyRow = document.getElementById("hist-empty");
    var info = document.getElementById("hist-info");
    var pager = document.getElementById("hist-pager");
    var chips = document.querySelectorAll(".hist-chip");

    var filter = "all";
    var page = 1;

    function visibleRows() {
        return rows.filter(function (row) {
            return filter === "all" || row.dataset.status === filter;
        });
    }

    function pageButton(label, target, opts) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "hist-page" + (opts && opts.active ? " is-active" : "");
        btn.textContent = label;
        btn.disabled = !!(opts && opts.disabled);
        if (opts && opts.aria) btn.setAttribute("aria-label", opts.aria);
        btn.addEventListener("click", function () {
            page = target;
            render();
        });
        return btn;
    }

    function render() {
        var list = visibleRows();
        var pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
        if (page > pages) page = pages;

        var start = (page - 1) * PER_PAGE;
        var shown = list.slice(start, start + PER_PAGE);

        rows.forEach(function (row) {
            row.hidden = shown.indexOf(row) === -1;
        });
        emptyRow.hidden = list.length !== 0;

        info.textContent = list.length
            ? "Menampilkan " + (start + 1) + "–" + (start + shown.length) +
              " dari " + list.length + " penjemputan"
            : "Tidak ada penjemputan";

        pager.innerHTML = "";
        if (pages < 2) return;
        pager.appendChild(pageButton("‹", page - 1, { disabled: page === 1, aria: "Halaman sebelumnya" }));
        for (var i = 1; i <= pages; i++) {
            pager.appendChild(pageButton(String(i), i, { active: i === page }));
        }
        pager.appendChild(pageButton("›", page + 1, { disabled: page === pages, aria: "Halaman berikutnya" }));
    }

    chips.forEach(function (chip) {
        chip.addEventListener("click", function () {
            filter = chip.dataset.filter;
            page = 1;
            chips.forEach(function (c) {
                var on = c === chip;
                c.classList.toggle("is-active", on);
                c.setAttribute("aria-selected", on ? "true" : "false");
            });
            render();
        });
    });

    // Unduh CSV: semua baris pada filter aktif (bukan hanya halaman ini)
    document.getElementById("hist-download").addEventListener("click", function () {
        var head = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) {
            return th.textContent.trim();
        });
        var lines = [head].concat(visibleRows().map(function (row) {
            return Array.prototype.map.call(row.cells, function (td) {
                return td.textContent.replace(/\s+/g, " ").trim();
            });
        }));
        var csv = lines.map(function (cells) {
            return cells.map(function (c) { return '"' + c.replace(/"/g, '""') + '"'; }).join(",");
        }).join("\r\n");

        var blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "riwayat-pikap.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
    });

    render();
})();