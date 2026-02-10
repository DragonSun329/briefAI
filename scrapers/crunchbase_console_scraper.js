/**
 * Crunchbase Console Scraper v6 (2026 Update)
 *
 * Paste this into browser DevTools console (F12) while on Crunchbase Discover page.
 *
 * Usage:
 * 1. Go to https://www.crunchbase.com/discover/organization.companies
 * 2. Click "Edit Columns" and add: Headquarters Location, CB Rank, Total Funding, etc.
 * 3. Apply filters (AI/ML companies)
 * 4. Open DevTools (F12) -> Console
 * 5. Paste this entire script and press Enter
 * 6. Scroll down to load more companies, run `scrapeCurrentPage()` again
 * 7. When done, run `downloadResults()` to save JSON
 */

// Global storage
window.scrapedCompanies = window.scrapedCompanies || {};

function scrapeCurrentPage() {
    const results = [];

    // Find all grid-row elements (custom Angular elements)
    const gridRows = document.querySelectorAll('grid-row');
    console.log(`Found ${gridRows.length} grid-row elements`);

    // Skip first row (header)
    for (let i = 1; i < gridRows.length; i++) {
        const row = gridRows[i];
        const cells = row.querySelectorAll('grid-cell');

        if (cells.length === 0) continue;

        const company = {};

        // Extract data from each cell
        cells.forEach((cell, idx) => {
            const text = cell.innerText?.trim() || '';
            if (!text || text === '-' || text === '—') return;

            // Check for organization link (company name)
            const orgLink = cell.querySelector('a[href*="/organization/"]');
            if (orgLink && !company.name) {
                company.name = orgLink.innerText?.trim();
                company.url = orgLink.href;
                return;
            }

            // Content-based detection
            assignFieldByContent(company, text, idx);
        });

        if (company.name) {
            results.push(company);
        }
    }

    // Merge with existing results
    let newCount = 0;
    let updatedCount = 0;
    results.forEach(company => {
        const key = company.name?.toLowerCase().trim();
        if (key) {
            if (!window.scrapedCompanies[key]) {
                window.scrapedCompanies[key] = company;
                newCount++;
            } else {
                const existing = window.scrapedCompanies[key];
                let updated = false;
                for (const [k, v] of Object.entries(company)) {
                    if (v && !existing[k]) {
                        existing[k] = v;
                        updated = true;
                    }
                }
                if (updated) updatedCount++;
            }
        }
    });

    const total = Object.keys(window.scrapedCompanies).length;
    console.log(`✅ Scraped ${results.length} rows, ${newCount} new, ${updatedCount} updated. Total: ${total}`);

    // Show sample
    if (results.length > 0) {
        const sample = results.slice(0, 3);
        console.log('\nSample data:');
        sample.forEach(c => {
            console.log(`  ${c.name}`);
            console.log(`    Location: ${c.hq_location || 'N/A'} → Country: ${c.country || 'N/A'}`);
            console.log(`    Funding: ${c.funding_total || 'N/A'} | Rank: ${c.cb_rank || 'N/A'}`);
        });
    }

    return results;
}

function assignFieldByContent(company, text, cellIndex) {
    if (!text || text === '-' || text === '—') return;

    // CB Rank (number 1-999999)
    if (/^[\d,]{1,7}$/.test(text) && !company.cb_rank) {
        const num = parseInt(text.replace(/,/g, ''));
        if (num > 0 && num < 1000000) {
            company.cb_rank = num;
            return;
        }
    }

    // Funding ($XXM, $XXB, $XXK)
    if (/^\$[\d,.]+[MBK]?$/i.test(text) && !company.funding_total) {
        company.funding_total = text;
        company.funding_usd = parseFunding(text);
        return;
    }

    // Revenue ranges ($10M to $50M)
    if (/\$[\d.]+[MBK]?\s*to\s*\$[\d.]+[MBK]?/i.test(text) && !company.estimated_revenue) {
        company.estimated_revenue = text;
        return;
    }

    // Date patterns (Jan 6, 2026 or Aug 2022)
    if (/^[A-Z][a-z]{2,8}\s+\d{1,2},?\s*\d{4}$/i.test(text) ||
        /^[A-Z][a-z]{2,8}\s+\d{4}$/i.test(text)) {
        if (!company.last_funding_date) {
            company.last_funding_date = text;
        } else if (!company.founded_date) {
            company.founded_date = text;
            const yearMatch = text.match(/(19|20)\d{2}/);
            if (yearMatch) company.founded_year = parseInt(yearMatch[0]);
        }
        return;
    }

    // Year only (2017)
    if (/^(19|20)\d{2}$/.test(text) && !company.founded_year) {
        company.founded_year = parseInt(text);
        company.founded_date = text;
        return;
    }

    // Employee count (1001-5000, 51-100, 10001+)
    if ((/^\d+-\d+$/.test(text) || /^\d+\+$/.test(text)) && !company.employees) {
        company.employees = text;
        return;
    }

    // Funding type (Series A, Seed, etc.)
    if (/^(Seed|Series\s*[A-Z]|Pre-Seed|Grant|Debt|IPO|Post-IPO|Corporate|Undisclosed|Angel|Convertible)/i.test(text) && !company.last_funding_type) {
        company.last_funding_type = text;
        return;
    }

    // Operating status
    if (/^(Active|Closed|Acquired|IPO)$/i.test(text) && !company.operating_status) {
        company.operating_status = text;
        return;
    }

    // Growth/Heat score tiers
    if (/^(High|Medium|Low)$/i.test(text)) {
        if (!company.growth_score) {
            company.growth_score = text;
        } else if (!company.heat_score) {
            company.heat_score = text;
        }
        return;
    }

    // Trend score (decimal like 3.7, -0.5)
    if (/^-?[\d.]+$/.test(text) && text.includes('.') && !company.trend_score) {
        const num = parseFloat(text);
        if (!isNaN(num) && num >= -100 && num <= 100) {
            company.trend_score = num;
        }
        return;
    }

    // Region pattern - detect FIRST before location (Bay Area, West Coast, etc.)
    // These are NOT actual locations, just regions
    const regionPatterns = /Bay Area|Silicon Valley|Greater|West Coast|East Coast|Midwest|Southern US|Western US|Northeastern US|New England|EMEA|APAC|Middle East|Latin America|Northern Europe|Southeast Asia|North Africa/i;
    if (regionPatterns.test(text) && !company.hq_region) {
        company.hq_region = text;
        return;
    }

    // Location: City, State, Country (e.g., "Palo Alto, California, United States")
    // Must contain actual country names at the END
    const countryNames = /United States|China|United Kingdom|Germany|France|Canada|Israel|India|Japan|Singapore|Australia|Netherlands|Sweden|Switzerland|South Korea|Brazil|Spain|Italy|Ireland|Belgium|Austria|Finland|Norway|Denmark|Poland|Taiwan|Hong Kong|Indonesia|Thailand|Vietnam|Malaysia|Philippines|Mexico|Argentina|Chile|Colombia|UAE|Saudi Arabia|Egypt|Nigeria|South Africa|New Zealand|Portugal|Czech Republic|Hungary|Romania|Greece|Turkey|Russia|Ukraine/i;
    if (/^[A-Za-z][A-Za-z\s.-]+,\s*[A-Za-z][A-Za-z\s.-]+,\s*[A-Za-z][A-Za-z\s]+$/.test(text) && !company.hq_location) {
        const parts = text.split(',').map(p => p.trim());
        const lastPart = parts[parts.length - 1];
        // Only accept if the last part is a real country
        if (countryNames.test(lastPart)) {
            company.hq_location = text;
            company.city = parts[0];
            company.state = parts[1];
            company.country = lastPart;
            return;
        }
    }

    // Location: City, Country (2 parts) - must have real country at end
    if (/^[A-Za-z][A-Za-z\s.-]+,\s*[A-Za-z][A-Za-z\s]+$/.test(text) && text.length > 5 && text.length < 60 && !company.hq_location) {
        const parts = text.split(',').map(p => p.trim());
        const lastPart = parts[parts.length - 1];
        // Only accept if last part is a real country
        if (countryNames.test(lastPart) && !/Series|Seed|Grant|Debt|IPO/i.test(text)) {
            company.hq_location = text;
            company.city = parts[0];
            company.country = lastPart;
            return;
        }
    }

    // Industries (long text with commas, or AI/ML keywords)
    if ((text.includes(',') || /artificial intelligence|machine learning/i.test(text)) && text.length > 20 && !company.industries) {
        company.industries = text;
        return;
    }

    // Number of funding rounds (1-50)
    if (/^\d{1,2}$/.test(text)) {
        const num = parseInt(text);
        if (num > 0 && num <= 50 && !company.funding_rounds) {
            company.funding_rounds = num;
        }
    }
}

function parseFunding(text) {
    if (!text) return null;
    let cleaned = text.replace(/[$,]/g, '').trim();
    if (/[\d.]+\s*B/i.test(cleaned)) {
        return parseFloat(cleaned.match(/([\d.]+)/)[1]) * 1e9;
    }
    if (/[\d.]+\s*M/i.test(cleaned)) {
        return parseFloat(cleaned.match(/([\d.]+)/)[1]) * 1e6;
    }
    if (/[\d.]+\s*K/i.test(cleaned)) {
        return parseFloat(cleaned.match(/([\d.]+)/)[1]) * 1e3;
    }
    const num = parseFloat(cleaned);
    return isNaN(num) ? null : num;
}

function downloadResults() {
    const companies = Object.values(window.scrapedCompanies);
    if (companies.length === 0) {
        console.warn('No companies to download. Run scrapeCurrentPage() first.');
        return;
    }

    companies.sort((a, b) => (a.cb_rank || 99999) - (b.cb_rank || 99999));

    const json = JSON.stringify(companies, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const today = new Date().toISOString().split('T')[0];
    const filename = `crunchbase_ai_companies_${today}.json`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    console.log(`✅ Downloaded ${companies.length} companies to ${filename}`);
    showStats();
}

function clearResults() {
    window.scrapedCompanies = {};
    console.log('Cleared all scraped data');
}

function showStats() {
    const companies = Object.values(window.scrapedCompanies);
    const withRank = companies.filter(c => c.cb_rank).length;
    const withFunding = companies.filter(c => c.funding_total).length;
    const withLocation = companies.filter(c => c.hq_location).length;
    const withCountry = companies.filter(c => c.country).length;
    const withRevenue = companies.filter(c => c.estimated_revenue).length;
    const withEmployees = companies.filter(c => c.employees).length;

    // Country breakdown
    const countryCounts = {};
    companies.forEach(c => {
        if (c.country) {
            countryCounts[c.country] = (countryCounts[c.country] || 0) + 1;
        }
    });

    console.log('\n📊 Scrape Statistics:');
    console.log(`   Total: ${companies.length}`);
    console.log(`   With CB Rank: ${withRank}`);
    console.log(`   With Location: ${withLocation}`);
    console.log(`   With Country: ${withCountry}`);
    console.log(`   With Funding: ${withFunding}`);
    console.log(`   With Revenue: ${withRevenue}`);
    console.log(`   With Employees: ${withEmployees}`);

    if (Object.keys(countryCounts).length > 0) {
        console.log('\n📍 Top Countries:');
        Object.entries(countryCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10)
            .forEach(([country, count]) => {
                console.log(`   ${country}: ${count}`);
            });
    }
}

// Auto-run
console.log('');
console.log('═══════════════════════════════════════════════════════════════');
console.log('  CRUNCHBASE CONSOLE SCRAPER v6');
console.log('═══════════════════════════════════════════════════════════════');
console.log('');
console.log('Commands:');
console.log('  scrapeCurrentPage()  - Scrape visible rows');
console.log('  downloadResults()    - Download JSON file');
console.log('  showStats()          - Show statistics');
console.log('  clearResults()       - Clear all data');
console.log('');
console.log('═══════════════════════════════════════════════════════════════');
console.log('');

scrapeCurrentPage();