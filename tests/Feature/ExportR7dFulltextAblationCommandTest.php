<?php

namespace Tests\Feature;

use App\Models\NewsArticle;
use App\Models\SentimentManualLabel;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class ExportR7dFulltextAblationCommandTest extends TestCase
{
    use RefreshDatabase;

    protected string $outputDir;

    protected function setUp(): void
    {
        parent::setUp();
        $this->outputDir = 'data/evaluation/_test_r7d_ablation';
        File::deleteDirectory(base_path($this->outputDir));
    }

    protected function tearDown(): void
    {
        File::deleteDirectory(base_path($this->outputDir));
        parent::tearDown();
    }

    protected function labelArticle(string $label, bool $withFullText = true, ?string $fullText = null): void
    {
        $user = User::factory()->create();
        $article = NewsArticle::factory()->create([
            'title' => 'Judul berita '.uniqid(),
            'summary' => 'Ringkasan singkat berita.',
            'full_text' => $withFullText ? ($fullText ?? str_repeat('Isi lengkap artikel. ', 20)) : null,
        ]);
        SentimentManualLabel::create([
            'news_article_id' => $article->id,
            'user_id' => $user->id,
            'label' => $label,
        ]);
    }

    public function test_it_exports_two_variants_with_matching_splits(): void
    {
        foreach (['positive', 'negative', 'neutral'] as $label) {
            for ($i = 0; $i < 4; $i++) {
                $this->labelArticle($label);
            }
        }

        $this->artisan('sentiment:export-r7d-fulltext-ablation', [
            '--output-dir' => $this->outputDir,
            '--train-ratio' => 0.5,
            '--val-ratio' => 0.25,
        ])->assertExitCode(0);

        $this->assertFileExists(base_path($this->outputDir.'/title_summary/train.jsonl'));
        $this->assertFileExists(base_path($this->outputDir.'/title_summary_fulltext/train.jsonl'));

        $baseline = collect(explode("\n", trim(file_get_contents(base_path($this->outputDir.'/title_summary/train.jsonl')))))
            ->map(fn ($line) => json_decode($line, true));
        $fulltext = collect(explode("\n", trim(file_get_contents(base_path($this->outputDir.'/title_summary_fulltext/train.jsonl')))))
            ->map(fn ($line) => json_decode($line, true));

        // Same rows/split across both variants -- only text construction differs.
        $this->assertSame($baseline->pluck('news_article_id')->sort()->values()->all(), $fulltext->pluck('news_article_id')->sort()->values()->all());
        $this->assertSame($baseline->pluck('label')->sort()->values()->all(), $fulltext->pluck('label')->sort()->values()->all());

        foreach ($fulltext as $row) {
            $this->assertStringContainsString('Isi lengkap artikel', $row['text']);
        }
        foreach ($baseline as $row) {
            $this->assertStringNotContainsString('Isi lengkap artikel', $row['text']);
        }
    }

    public function test_it_excludes_rows_without_full_text(): void
    {
        $this->labelArticle('positive', withFullText: true);
        $this->labelArticle('positive', withFullText: false);

        $this->artisan('sentiment:export-r7d-fulltext-ablation', [
            '--output-dir' => $this->outputDir,
        ])->assertExitCode(0);

        $all = collect(['train', 'val', 'test'])->flatMap(function ($split) {
            $path = base_path($this->outputDir."/title_summary/{$split}.jsonl");
            if (! file_exists($path) || trim(file_get_contents($path)) === '') {
                return [];
            }

            return collect(explode("\n", trim(file_get_contents($path))))->map(fn ($line) => json_decode($line, true));
        });

        $this->assertCount(1, $all);
    }
}
