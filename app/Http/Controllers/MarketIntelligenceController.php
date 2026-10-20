<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;

class MarketIntelligenceController extends Controller
{
    /**
     * Display a listing of market intelligence & regime research reports.
     */
    public function index()
    {
        $reports = $this->getAvailableReports();
        
        $latestRegime = [
            'status' => 'TRANSISI REBOUND SPEKULATIF (TIER 1)',
            'severity' => 'amber',
            'headline' => 'Transisi Rebound Spekulatif: Rebound Impulsif IHSG +3,61% & Skenario Masuk Sesi 2',
            'description' => 'IHSG melonjak +3,61% ke 5.181 dengan 85,4% saham menguat dan 0 saham ARB. Kunci 1 & 2 GEMINI.md valid. Sesuai hasil backtest empiris kuantitatif, entri akumulasi Tier 1 (15-20% kas) direkomendasikan dieksekusi di akhir Sesi 2 (14:45 - 15:45 WIB) dengan Stop Loss ketat -3,5%.',
            'ihsg_close' => '5.181,48',
            'ihsg_change' => '+3,61%',
            'rsi_14' => '25,08',
            'ma20_dev' => '-12,86%',
            'market_breadth' => '85,4% Gainers (41 Naik vs 7 Turun | 0 ARB)',
            'key_catalyst' => 'BEI Hapus Saham HSC & Rebound Big Banks Serentak',
            'rebound_window' => 'Sesi 2 Hari Ini (14:45 - 15:45 WIB)',
            'last_updated' => '20 Oktober 2026 (Sesi 1 Siang)',
        ];

        return view('market-intelligence.index', [
            'reports' => $reports,
            'latestRegime' => $latestRegime,
        ]);
    }

    /**
     * Display the specified research report.
     */
    public function show(string $slug)
    {
        $filePath = base_path("reports/{$slug}.md");

        if (!File::exists($filePath)) {
            abort(404, 'Laporan riset pasar tidak ditemukan.');
        }

        $rawContent = File::get($filePath);
        $metadata = $this->parseReportMetadata(basename($filePath), $rawContent);

        // Convert markdown to clean HTML
        $htmlContent = Str::markdown($rawContent);

        // Enhance HTML styling for tables, blockquotes, and lists
        $htmlContent = $this->styleHtmlContent($htmlContent);

        $otherReports = collect($this->getAvailableReports())
            ->where('slug', '!=', $slug)
            ->take(4)
            ->values();

        return view('market-intelligence.show', [
            'metadata' => $metadata,
            'htmlContent' => $htmlContent,
            'rawContent' => $rawContent,
            'otherReports' => $otherReports,
        ]);
    }

    /**
     * Retrieve and parse all available research reports from reports/ directory.
     */
    protected function getAvailableReports(): array
    {
        $files = glob(base_path('reports/*.md'));
        $reports = [];

        foreach ($files as $file) {
            $filename = basename($file);
            $slug = pathinfo($filename, PATHINFO_FILENAME);
            $content = File::get($file);
            
            $metadata = $this->parseReportMetadata($filename, $content);
            if ($metadata['is_public']) {
                $reports[] = $metadata;
            }
        }

        // Sort descending by priority date / created time
        usort($reports, function ($a, $b) {
            return strcmp($b['sort_key'], $a['sort_key']);
        });

        return $reports;
    }

    /**
     * Parse metadata from report markdown content.
     */
    protected function parseReportMetadata(string $filename, string $content): array
    {
        $slug = pathinfo($filename, PATHINFO_FILENAME);

        // Title from first # heading
        preg_match('/^#\s+(.+)$/m', $content, $titleMatch);
        $title = isset($titleMatch[1]) ? trim($titleMatch[1]) : Str::headline($slug);

        // Date from **Tanggal Riset**:
        preg_match('/Tanggal Riset\*\*:\s*([^\n\r]+)/', $content, $dateMatch);
        $date = isset($dateMatch[1]) ? trim(str_replace(['*', '_'], '', $dateMatch[1])) : 'Oktober 2026';

        // Regime Status
        preg_match('/Status Rezim[^\*]*\*\*:\s*([^\n\r]+)/', $content, $regimeMatch);
        $regime = isset($regimeMatch[1]) ? trim(str_replace(['*', '_'], '', $regimeMatch[1])) : 'Market Research';

        // Extract Executive Summary / lead paragraph
        preg_match('/## 1\.\s*Eksekutif Ringkasan\s*\n\s*([^\n#]+)/m', $content, $summaryMatch);
        if (!isset($summaryMatch[1])) {
            preg_match('/\n\n([A-Z][^\n#]{60,250}\.)/m', $content, $summaryMatch);
        }
        $summary = isset($summaryMatch[1]) ? Str::limit(trim($summaryMatch[1]), 180) : 'Kajian analisis komprehensif rezim pasar saham Indonesia, metrik teknikal, dan evaluasi risiko kuantitatif.';

        // Word count & read time
        $wordCount = str_word_count(strip_tags($content));
        $readTime = max(2, ceil($wordCount / 180));

        // Category & Tagging
        $isFeatured = ($slug === 'market_regime_research_20261020');
        $tag = 'Analisis Rezim';
        $tagColor = 'rose';

        if ($slug === 'market_regime_research_20261020') {
            $tag = 'Rebound & Backtest Sesi';
            $tagColor = 'emerald';
        } elseif (str_contains($slug, 'rebound_prediction')) {
            $tag = 'Proyeksi Rebound & MSCI';
            $tagColor = 'amber';
        } elseif (str_contains($slug, 'screener')) {
            $tag = 'Screener Saham';
            $tagColor = 'cyan';
        } elseif (str_contains($slug, '19')) {
            $tag = 'Kapitulasi Pasar';
            $tagColor = 'rose';
        } elseif (str_contains($slug, '16')) {
            $tag = 'Flash Crash Audit';
            $tagColor = 'red';
        }

        // Sort key based on filename date pattern
        preg_match('/\d{8}/', $slug, $numMatch);
        $sortKey = (isset($numMatch[0]) ? $numMatch[0] : '20261001') . ($slug === 'market_regime_research_20261020' ? '9' : '1');

        // Hide internal test candidate file from public research list
        $isPublic = !str_contains($slug, 'official_test');

        return [
            'slug' => $slug,
            'title' => $title,
            'date' => $date,
            'regime' => $regime,
            'summary' => $summary,
            'read_time' => $readTime,
            'tag' => $tag,
            'tag_color' => $tagColor,
            'is_featured' => $isFeatured,
            'sort_key' => $sortKey,
            'is_public' => $isPublic,
            'file_size' => round(strlen($content) / 1024, 1) . ' KB',
        ];
    }

    /**
     * Add modern custom classes to markdown generated HTML.
     */
    protected function styleHtmlContent(string $html): string
    {
        // Tables
        $html = str_replace('<table>', '<div class="table-responsive my-6 overflow-x-auto rounded-xl border border-slate-700/60 bg-slate-900/40"><table class="w-full text-left border-collapse text-xs">', $html);
        $html = str_replace('</table>', '</table></div>', $html);
        $html = str_replace('<th>', '<th class="p-3 bg-slate-800/80 text-slate-200 font-semibold border-b border-slate-700">', $html);
        $html = str_replace('<td>', '<td class="p-3 border-b border-slate-800/60 text-slate-300">', $html);

        // Blockquotes
        $html = str_replace('<blockquote>', '<blockquote class="border-l-4 border-amber-500 bg-amber-500/10 p-4 rounded-r-xl my-4 text-amber-200 text-xs">', $html);

        // Pre / Code
        $html = str_replace('<pre><code>', '<div class="my-4 rounded-xl border border-slate-700 bg-slate-950 p-4 overflow-x-auto text-xs font-mono text-emerald-400"><code>', $html);
        $html = str_replace('</code></pre>', '</code></div>', $html);

        return $html;
    }
}
