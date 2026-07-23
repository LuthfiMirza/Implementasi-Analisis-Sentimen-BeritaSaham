<?php

namespace Tests\Unit;

use PHPUnit\Framework\TestCase;

class EvaluationContractVerifierTest extends TestCase
{
    private string $tempDir;

    protected function setUp(): void
    {
        parent::setUp();
        $this->tempDir = sys_get_temp_dir().'/sentiment_eval_contract_'.bin2hex(random_bytes(6));
        mkdir($this->tempDir, 0777, true);
    }

    protected function tearDown(): void
    {
        $this->removeDirectory($this->tempDir);
        parent::tearDown();
    }

    public function test_valid_manifest_passes_and_is_read_only(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'positive'],
            ['article_id' => '2', 'label' => 'neutral'],
            ['article_id' => '3', 'label' => 'negative'],
        ]);

        $before = $this->listFiles($this->tempDir);
        $result = $this->runVerifier($manifest, $checksum, 3, ['positive' => 1, 'neutral' => 1, 'negative' => 1]);
        $after = $this->listFiles($this->tempDir);

        $this->assertSame(0, $result['exit']);
        $this->assertStringContainsString('"read_only": true', $result['output']);
        $this->assertSame($before, $after);
    }

    public function test_checksum_mismatch_is_rejected(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'positive'],
        ]);
        file_put_contents($manifest, "article_id,label\n1,neutral\n");

        $result = $this->runVerifier($manifest, $checksum, 1, ['positive' => 1, 'neutral' => 0, 'negative' => 0]);

        $this->assertNotSame(0, $result['exit']);
        $this->assertStringContainsString('checksum mismatch', $result['output']);
    }

    public function test_duplicate_article_id_is_rejected(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'positive'],
            ['article_id' => '1', 'label' => 'neutral'],
        ]);

        $result = $this->runVerifier($manifest, $checksum, 2, ['positive' => 1, 'neutral' => 1, 'negative' => 0]);

        $this->assertNotSame(0, $result['exit']);
        $this->assertStringContainsString('duplicate article_id', $result['output']);
    }

    public function test_invalid_label_is_rejected(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'mixed'],
        ]);

        $result = $this->runVerifier($manifest, $checksum, 1, ['positive' => 0, 'neutral' => 0, 'negative' => 1]);

        $this->assertNotSame(0, $result['exit']);
        $this->assertStringContainsString('invalid labels', $result['output']);
    }

    public function test_row_count_mismatch_is_rejected(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'positive'],
        ]);

        $result = $this->runVerifier($manifest, $checksum, 2, ['positive' => 1, 'neutral' => 0, 'negative' => 0]);

        $this->assertNotSame(0, $result['exit']);
        $this->assertStringContainsString('row count mismatch', $result['output']);
    }

    public function test_validation_and_test_overlap_is_rejected(): void
    {
        [$manifest, $checksum] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'positive'],
        ]);
        [$validationManifest] = $this->writeManifest([
            ['article_id' => '1', 'label' => 'neutral'],
        ], 'validation.csv', 'validation.sha256');

        $result = $this->runVerifier(
            $manifest,
            $checksum,
            1,
            ['positive' => 1, 'neutral' => 0, 'negative' => 0],
            [$validationManifest]
        );

        $this->assertNotSame(0, $result['exit']);
        $this->assertStringContainsString('article_id overlap', $result['output']);
    }

    private function writeManifest(array $rows, string $manifestName = 'manifest.csv', string $checksumName = 'manifest.sha256'): array
    {
        $manifest = $this->tempDir.'/'.$manifestName;
        $checksum = $this->tempDir.'/'.$checksumName;
        $handle = fopen($manifest, 'wb');
        fputcsv($handle, ['article_id', 'label'], ',', '"', '');
        foreach ($rows as $row) {
            fputcsv($handle, [$row['article_id'], $row['label']], ',', '"', '');
        }
        fclose($handle);
        file_put_contents($checksum, hash_file('sha256', $manifest).'  '.$manifestName.PHP_EOL);

        return [$manifest, $checksum];
    }

    private function runVerifier(string $manifest, string $checksum, int $expectedRows, array $distribution, array $noOverlap = []): array
    {
        $command = [
            'python3',
            getcwd().'/scripts/verify_evaluation_contract.py',
            '--manifest',
            $manifest,
            '--checksum',
            $checksum,
            '--expected-rows',
            (string) $expectedRows,
            '--expected-distribution',
            json_encode($distribution),
        ];
        foreach ($noOverlap as $path) {
            $command[] = '--no-overlap-manifest';
            $command[] = $path;
        }

        $escaped = array_map('escapeshellarg', $command);
        exec(implode(' ', $escaped).' 2>&1', $output, $exitCode);

        return ['exit' => $exitCode, 'output' => implode("\n", $output)];
    }

    private function listFiles(string $dir): array
    {
        $files = array_values(array_diff(scandir($dir), ['.', '..']));
        sort($files);

        return $files;
    }

    private function removeDirectory(string $dir): void
    {
        if (! is_dir($dir)) {
            return;
        }
        foreach (array_diff(scandir($dir), ['.', '..']) as $item) {
            $path = $dir.'/'.$item;
            is_dir($path) ? $this->removeDirectory($path) : unlink($path);
        }
        rmdir($dir);
    }
}
