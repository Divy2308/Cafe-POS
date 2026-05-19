/**
 * Thermal printing: QZ Tray ESC/POS + browser print helpers for POS Cafe.
 * Depends on base.html loading qz-tray.js (optional; graceful if missing).
 */
(function (global) {
  'use strict';

  var SETTINGS_KEY = 'printer_settings';
  var SETUP_DISMISS_KEY = 'printer_setup_dismissed';
  var DEFAULTS = {
    printer_type: 'browser',
    paper_width: '58mm',
    auto_print: false,
    copies: 1,
    kitchen_ticket: false,
    preferred_printer_name: ''
  };

  function getPrinterSettings() {
    try {
      var raw = localStorage.getItem(SETTINGS_KEY);
      var o = raw ? JSON.parse(raw) : {};
      if (!o.preferred_printer_name) {
        var tp = localStorage.getItem('thermal_printer');
        if (tp) o.preferred_printer_name = tp;
      }
      return Object.assign({}, DEFAULTS, o);
    } catch (e) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function savePrinterSettings(s) {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(Object.assign(getPrinterSettings(), s)));
    } catch (e) {}
  }

  function escPosRaw(s) {
    return { type: 'raw', format: 'plain', data: s };
  }

  /** Columns: ~32 for 58mm, ~48 for 80mm (7x9 font) */
  function paperCols(settings) {
    var w = (settings && settings.paper_width) || '58mm';
    return String(w).indexOf('80') >= 0 ? 48 : 32;
  }

  function lineSep(cols) {
    return '-'.repeat(Math.min(cols, 32)) + '\n';
  }

  function padLine(left, right, cols) {
    left = String(left || '');
    right = String(right || '');
    var space = cols - left.length - right.length;
    if (space < 1) return left.slice(0, cols - right.length - 1) + ' ' + right + '\n';
    return left + ' '.repeat(space) + right + '\n';
  }

  function buildESCPOSReceipt(order, cafe, settings) {
    var ESC = '\x1B';
    var GS = '\x1D';
    var cols = paperCols(settings || getPrinterSettings());
    var data = [];
    data.push(escPosRaw(ESC + '@'));
    data.push(escPosRaw(ESC + 'a' + '\x01'));
    data.push(escPosRaw(ESC + 'E' + '\x01'));
    data.push(escPosRaw((cafe.invoice_title || 'TAX INVOICE') + '\n'));
    data.push(escPosRaw(ESC + 'E' + '\x00'));
    data.push(escPosRaw(ESC + '!' + '\x10'));
    data.push(escPosRaw((cafe.name || 'POS Cafe') + '\n'));
    data.push(escPosRaw(ESC + '!' + '\x00'));
    if (cafe.address) data.push(escPosRaw(cafe.address + '\n'));
    if (cafe.phone) data.push(escPosRaw('Ph: ' + cafe.phone + '\n'));
    if (cafe.gst_no) data.push(escPosRaw('GST: ' + cafe.gst_no + '\n'));
    if (cafe.fssai_no) data.push(escPosRaw('FSSAI: ' + cafe.fssai_no + '\n'));
    data.push(escPosRaw(lineSep(cols)));
    data.push(escPosRaw(ESC + 'a' + '\x00'));
    var dt = order.created_at ? new Date(order.created_at) : new Date();
    data.push(escPosRaw('Order: ' + (order.order_number || '') + '\n'));
    data.push(escPosRaw('Table: ' + (order.table || 'Takeaway') + '\n'));
    data.push(escPosRaw('Date: ' + dt.toLocaleString() + '\n'));
    data.push(escPosRaw(lineSep(cols)));
    var h1 = 'Item'.padEnd(Math.min(18, cols - 14));
    data.push(escPosRaw(h1 + 'Qty' + '  Amt\n'));
    data.push(escPosRaw(lineSep(cols)));
    (order.items || []).forEach(function (item) {
      var name = (item.name || '').replace(/[\x00-\x1F]/g, '');
      var lineAmt = (item.price * item.qty).toFixed(2);
      var maxN = cols - 12;
      var row = name.length > maxN ? name.slice(0, maxN - 1) + '\u2026' : name;
      row = row.padEnd(Math.min(18, cols - 14));
      var qty = String(item.qty || 0).padStart(3);
      var amt = lineAmt.padStart(8);
      data.push(escPosRaw(row + qty + amt + '\n'));
      if (item.notes) data.push(escPosRaw('  * ' + String(item.notes).slice(0, cols - 4) + '\n'));
    });
    data.push(escPosRaw(lineSep(cols)));
    var sub = Number(order.subtotal != null ? order.subtotal : 0);
    data.push(escPosRaw(padLine('Subtotal', 'Rs.' + sub.toFixed(2), cols)));
    if (cafe.show_tax_rows !== false && order.tax_breakdown && typeof order.tax_breakdown === 'object') {
      Object.keys(order.tax_breakdown).forEach(function (k) {
        var v = order.tax_breakdown[k];
        data.push(escPosRaw(padLine(k, 'Rs.' + Number(v).toFixed(2), cols)));
      });
    }
    if (cafe.show_round_off !== false && order.round_off) {
      data.push(escPosRaw(padLine('Round off', 'Rs.' + Number(order.round_off).toFixed(2), cols)));
    }
    if (order.discount_amount) {
      var discountLabel = 'Discount';
      if (order.coupon_code) discountLabel += ' (' + order.coupon_code + ')';
      data.push(escPosRaw(padLine(discountLabel, '-Rs.' + Number(order.discount_amount).toFixed(2), cols)));
    }
    if (order.loyalty_points_used) {
      data.push(escPosRaw(padLine('Loyalty Used', '-Rs.' + Number(order.loyalty_points_used).toFixed(2), cols)));
    }
    if (order.tip) {
      data.push(escPosRaw(padLine('Tip', 'Rs.' + Number(order.tip).toFixed(2), cols)));
    }
    var grand = order.grand_total != null ? Number(order.grand_total) : Number(order.total || 0);
    data.push(escPosRaw('================================\n'));
    data.push(escPosRaw(ESC + 'E' + '\x01'));
    data.push(escPosRaw(ESC + '!' + '\x30'));
    data.push(escPosRaw('TOTAL: Rs.' + grand.toFixed(0) + '\n'));
    data.push(escPosRaw(ESC + '!' + '\x00'));
    data.push(escPosRaw(ESC + 'E' + '\x00'));
    var pm = order.payment_method || '—';
    data.push(escPosRaw('Payment: ' + pm + '\n'));
    data.push(escPosRaw(lineSep(cols)));
    data.push(escPosRaw(ESC + 'a' + '\x01'));
    data.push(escPosRaw((cafe.footer_note || 'Thank you! Visit again.') + '\n'));
    data.push(escPosRaw('\n\n\n'));
    data.push(escPosRaw(GS + 'V' + '\x01'));
    return data;
  }

  function buildKitchenTicketESCPOS(order, cafe, settings) {
    var ESC = '\x1B';
    var GS = '\x1D';
    var cols = paperCols(settings || getPrinterSettings());
    var data = [];
    data.push(escPosRaw(ESC + '@'));
    data.push(escPosRaw(ESC + 'a' + '\x01'));
    data.push(escPosRaw(ESC + '!' + '\x30'));
    data.push(escPosRaw('KITCHEN ORDER\n'));
    data.push(escPosRaw(ESC + '!' + '\x00'));
    data.push(escPosRaw(ESC + 'E' + '\x01'));
    data.push(escPosRaw((order.order_number || '') + '\n'));
    data.push(escPosRaw(ESC + 'E' + '\x00'));
    data.push(escPosRaw('Table: ' + (order.table || 'Takeaway') + '\n'));
    var dt = order.created_at ? new Date(order.created_at) : new Date();
    data.push(escPosRaw(dt.toLocaleTimeString() + '\n'));
    data.push(escPosRaw(lineSep(cols)));
    data.push(escPosRaw(ESC + 'a' + '\x00'));
    data.push(escPosRaw(ESC + '!' + '\x11'));
    (order.items || []).forEach(function (item) {
      var line = 'x' + (item.qty || 0) + ' ' + (item.name || '');
      if (item.notes) line += '\n   >> ' + item.notes;
      data.push(escPosRaw(line.slice(0, cols * 2) + '\n'));
    });
    data.push(escPosRaw(ESC + '!' + '\x00'));
    data.push(escPosRaw('\n\n'));
    data.push(escPosRaw(GS + 'V' + '\x01'));
    return data;
  }

  async function fetchReceiptDataForPrint(orderId) {
    var r = await fetch('/api/receipt-data/' + orderId, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error('Failed to load receipt data');
    return r.json();
  }

  async function printWithQZTray(order, cafeSettings, settings) {
    if (typeof qz === 'undefined' || !qz.websocket) {
      throw new Error('QZ Tray not loaded');
    }
    await qz.websocket.connect();
    var printers = await qz.printers.find();
    if (!printers || !printers.length) throw new Error('No printers found');
    var preferred = (settings && settings.preferred_printer_name) || localStorage.getItem('thermal_printer') || printers[0];
    if (printers.indexOf(preferred) < 0) preferred = printers[0];
    var config = qz.configs.create(preferred, { copies: Math.min(9, (settings && settings.copies) || 1) });
    var data = buildESCPOSReceipt(order, cafeSettings, settings);
    await qz.print(config, data);
    try { await qz.websocket.disconnect(); } catch (e) {}
    return { ok: true };
  }

  async function printKitchenWithQZTray(order, cafeSettings, settings) {
    if (typeof qz === 'undefined' || !qz.websocket) throw new Error('QZ Tray not loaded');
    await qz.websocket.connect();
    var printers = await qz.printers.find();
    if (!printers || !printers.length) throw new Error('No printers found');
    var preferred = (settings && settings.preferred_printer_name) || localStorage.getItem('thermal_printer') || printers[0];
    if (printers.indexOf(preferred) < 0) preferred = printers[0];
    var config = qz.configs.create(preferred, { copies: 1 });
    var data = buildKitchenTicketESCPOS(order, cafeSettings, settings);
    await qz.print(config, data);
    try { await qz.websocket.disconnect(); } catch (e) {}
    return { ok: true };
  }

  function printReceiptBrowser(orderId, paper) {
    var p = paper || (getPrinterSettings().paper_width || '58mm').replace('mm', '');
    var url = '/receipt/' + orderId + '?print=1&paper=' + encodeURIComponent(p);
    var win = window.open(url, '_blank', 'width=420,height=720');
    return !!win;
  }

  function printKitchenBrowser(order, cafe) {
    var lines = (order.items || []).map(function (i) {
      return (i.qty || 0) + 'x  ' + (i.name || '') + (i.notes ? '  (' + i.notes + ')' : '');
    }).join('\n');
    var w = window.open('', '_blank', 'width=400,height=600');
    if (!w) return false;
    var esc = function (s) {
      var d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    };
    w.document.write('<!DOCTYPE html><html><head><title>Kitchen</title><style>body{font-family:monospace;padding:16px;font-size:18px;}pre{white-space:pre-wrap;margin:0}</style></head><body><h2>' +
      esc(cafe.name || 'Kitchen') + '</h2><h1>' + esc(order.order_number || '') + '</h1><p>Table ' + esc(String(order.table || '')) + '</p><pre>' + esc(lines) + '</pre><script>window.onload=function(){setTimeout(function(){window.print();},300);};<\/script></body></html>');
    w.document.close();
    return true;
  }

  async function autoPrintReceipt(orderId, extra) {
    var settings = getPrinterSettings();
    var payload;
    try {
      payload = await fetchReceiptDataForPrint(orderId);
    } catch (e) {
      console.error(e);
      printReceiptBrowser(orderId, settings.paper_width);
      return { ok: false, error: String(e.message || e) };
    }
    var order = payload.order;
    var cafe = payload.cafe;
    if (extra && extra.payment_method) order = Object.assign({}, order, { payment_method: extra.payment_method });
    if (settings.printer_type === 'qztray') {
      try {
        await printWithQZTray(order, cafe, settings);
      } catch (err) {
        console.error('QZ Tray error:', err);
        printReceiptBrowser(orderId, settings.paper_width);
        return { ok: false, error: err.message || String(err) };
      }
    } else {
      printReceiptBrowser(orderId, settings.paper_width);
    }
    return { ok: true };
  }

  async function maybeAutoPrintKitchenTicket(orderId) {
    var settings = getPrinterSettings();
    if (!settings.kitchen_ticket) return;
    var payload;
    try {
      payload = await fetchReceiptDataForPrint(orderId);
    } catch (e) {
      return;
    }
    try {
      if (settings.printer_type === 'qztray') {
        await printKitchenWithQZTray(payload.order, payload.cafe, settings);
      } else {
        printKitchenBrowser(payload.order, payload.cafe);
      }
    } catch (err) {
      console.error('Kitchen print:', err);
      printKitchenBrowser(payload.order, payload.cafe);
    }
  }

  function refreshPrinterStatus() {
    var dot = document.getElementById('printer-status-dot');
    var label = document.getElementById('printer-status-label');
    if (!dot || !label) return;
    var st = getPrinterSettings();
    if (st.printer_type === 'browser') {
      dot.className = 'w-2 h-2 rounded-full bg-amber-500 shrink-0';
      label.textContent = 'Print: browser';
      return;
    }
    if (typeof qz === 'undefined' || !qz.websocket) {
      dot.className = 'w-2 h-2 rounded-full bg-red-500 shrink-0';
      label.textContent = 'Print: QZ not loaded';
      return;
    }
    qz.websocket.connect().then(function () {
      return qz.printers.find();
    }).then(function (list) {
      dot.className = 'w-2 h-2 rounded-full ' + (list && list.length ? 'bg-emerald-500' : 'bg-red-500') + ' shrink-0';
      label.textContent = list && list.length ? 'Print: QZ ready' : 'Print: no printer';
      try { qz.websocket.disconnect(); } catch (e) {}
    }).catch(function () {
      dot.className = 'w-2 h-2 rounded-full bg-red-500 shrink-0';
      label.textContent = 'Print: QZ offline';
    });
  }

  global.getPrinterSettings = getPrinterSettings;
  global.savePrinterSettings = savePrinterSettings;
  global.buildESCPOSReceipt = buildESCPOSReceipt;
  global.buildKitchenTicketESCPOS = buildKitchenTicketESCPOS;
  global.printWithQZTray = printWithQZTray;
  global.fetchReceiptDataForPrint = fetchReceiptDataForPrint;
  global.autoPrintReceipt = autoPrintReceipt;
  global.maybeAutoPrintKitchenTicket = maybeAutoPrintKitchenTicket;
  global.refreshPrinterStatus = refreshPrinterStatus;
  global.printReceiptBrowser = printReceiptBrowser;
  global.PRINTER_SETUP_DISMISS_KEY = SETUP_DISMISS_KEY;
})(typeof window !== 'undefined' ? window : this);
