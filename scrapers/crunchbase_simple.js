(function(){
window.scrapedCompanies = window.scrapedCompanies || {};

window.scrapeCurrentPage = function() {
    var results = [];
    var rows = document.querySelectorAll('grid-row');

    if (rows.length === 0) {
        rows = document.querySelectorAll('tbody tr, [role="row"]');
        rows = Array.from(rows).filter(function(r) { return !r.closest('thead'); });
    }

    console.log('Found ' + rows.length + ' rows');

    rows.forEach(function(row) {
        var company = {};
        var cells = row.querySelectorAll('grid-cell, td, [role="gridcell"]');

        cells.forEach(function(cell, idx) {
            var text = (cell.innerText || '').trim();
            if (!text || text === '-') return;

            // Name (first cell with link)
            if (idx === 0 || cell.querySelector('a[href*="/organization/"]')) {
                var link = cell.querySelector('a[href*="/organization/"]');
                if (link && !company.name) {
                    company.name = link.innerText.trim();
                    company.url = link.href;
                }
            }

            // CB Rank (1-5 digit number)
            if (/^\d{1,5}$/.test(text.replace(/,/g, ''))) {
                var num = parseInt(text.replace(/,/g, ''));
                if (num > 0 && num < 100000) company.cb_rank = num;
            }

            // Funding ($XXB+, $XXM, etc)
            if (/^\$[\d,.]+[BMK]?\+?$/i.test(text) || /^\$[\d,]+$/.test(text)) {
                company.funding_total = text;
            }

            // Revenue range ($XM to $YM)
            if (/\$[\d.]+[MBK]?\s+to\s+\$[\d.]+[MBK]?/i.test(text)) {
                company.estimated_revenue = text;
            }

            // Founded date (Dec 8, 2015 or Jan 2021 or Apr 5, 1993 or just 2017)
            if (/^[A-Z][a-z]{2,8}\s+\d{1,2},?\s*\d{4}$/.test(text) ||
                /^[A-Z][a-z]{2,8}\s+\d{4}$/.test(text) ||
                /^(19|20)\d{2}$/.test(text)) {
                company.founded_date = text;
                var yearMatch = text.match(/(19|20)\d{2}/);
                if (yearMatch) company.founded_year = parseInt(yearMatch[0]);
            }

            // Employee range
            if (/^\d+-\d+$/.test(text) || /^\d{2,6}\+?$/.test(text)) {
                if (!company.employees && text.includes('-')) {
                    company.employees = text;
                }
            }
        });

        if (company.name) results.push(company);
    });

    var newCount = 0;
    results.forEach(function(c) {
        var key = (c.name || '').toLowerCase();
        if (key && !window.scrapedCompanies[key]) {
            window.scrapedCompanies[key] = c;
            newCount++;
        }
    });

    var total = Object.keys(window.scrapedCompanies).length;
    console.log('Scraped ' + results.length + ' rows, ' + newCount + ' new. Total: ' + total);

    if (results.length > 0) {
        var s = results[0];
        console.log('Sample: ' + s.name + ' | Funding: ' + (s.funding_total||'N/A') + ' | Revenue: ' + (s.estimated_revenue||'N/A') + ' | Founded: ' + (s.founded_year||'N/A'));
    }

    return results;
};

window.downloadResults = function() {
    var companies = Object.values(window.scrapedCompanies);
    if (companies.length === 0) { console.log('No data'); return; }

    companies.sort(function(a,b) { return (a.cb_rank||99999) - (b.cb_rank||99999); });

    var json = JSON.stringify(companies, null, 2);
    var blob = new Blob([json], {type: 'application/json'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'crunchbase_' + new Date().toISOString().split('T')[0] + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    console.log('Downloaded ' + companies.length + ' companies');
};

window.showStats = function() {
    var c = Object.values(window.scrapedCompanies);
    console.log('Total: ' + c.length);
    console.log('With Funding: ' + c.filter(function(x){return x.funding_total;}).length);
    console.log('With Revenue: ' + c.filter(function(x){return x.estimated_revenue;}).length);
    console.log('With Founded: ' + c.filter(function(x){return x.founded_year;}).length);
};

window.clearResults = function() {
    window.scrapedCompanies = {};
    console.log('Cleared');
};

console.log('=== CRUNCHBASE SCRAPER LOADED ===');
console.log('Commands: scrapeCurrentPage(), downloadResults(), showStats(), clearResults()');
scrapeCurrentPage();
})();