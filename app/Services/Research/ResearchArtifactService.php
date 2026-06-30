<?php

namespace App\Services\Research;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\File;
use InvalidArgumentException;

class ResearchArtifactService
{
    public const SUPPORTED_SCHEMAS = [
        'walk_forward' => 'walk_forward_v1',
        'tp_optimizer' => 'tp_optimizer_v1',
        'reentry' => 'reentry_v1',
        'decision' => 'trading_decision_v1',
        'notification' => 'trading_notification_v1',
        'learning' => 'trading_learning_v1',
    ];

    public function __construct(
        protected ?string $artifactRoot = null,
    ) {
        $this->artifactRoot ??= storage_path('app/trading_research');
    }

    public function load(string $path, ?string $expectedType = null, ?string $expectedTicker = null): array
    {
        if (! File::exists($path)) {
            throw new InvalidArgumentException("Research artifact not found: {$path}");
        }

        $payload = json_decode((string) File::get($path), true);
        if (! is_array($payload)) {
            throw new InvalidArgumentException("Research artifact is not valid JSON: {$path}");
        }

        $this->validatePayload($payload, $expectedType, $expectedTicker);

        return $payload;
    }

    public function available(string $path, ?string $expectedType = null, ?string $expectedTicker = null): array
    {
        try {
            return [
                'available' => true,
                'path' => $path,
                'artifact' => $this->load($path, $expectedType, $expectedTicker),
                'message' => null,
            ];
        } catch (InvalidArgumentException $exception) {
            return [
                'available' => false,
                'path' => $path,
                'artifact' => null,
                'message' => $exception->getMessage(),
            ];
        }
    }

    public function latest(string $artifactType, string $ticker, ?string $directory = null): array
    {
        $directory ??= $this->artifactRoot;
        $ticker = strtoupper(trim($ticker));
        $schema = self::SUPPORTED_SCHEMAS[$artifactType] ?? null;

        if ($schema === null) {
            throw new InvalidArgumentException("Unsupported artifact type: {$artifactType}");
        }

        if (! File::isDirectory($directory)) {
            return $this->unavailable($artifactType, $ticker, "Research artifact directory not found: {$directory}");
        }

        $matches = [];
        foreach (File::files($directory) as $file) {
            try {
                $payload = $this->load($file->getPathname(), $artifactType, $ticker);
            } catch (InvalidArgumentException) {
                continue;
            }

            if (($payload['schema_version'] ?? null) !== $schema) {
                continue;
            }

            $matches[] = [
                'path' => $file->getPathname(),
                'artifact' => $payload,
                'generated_at' => $this->generatedTimestamp($payload),
            ];
        }

        if ($matches === []) {
            return $this->unavailable($artifactType, $ticker, "No valid {$artifactType} artifact found for {$ticker} in {$directory}");
        }

        usort($matches, fn (array $left, array $right): int => $right['generated_at'] <=> $left['generated_at']);

        return [
            'available' => true,
            'artifact_type' => $artifactType,
            'ticker' => $ticker,
            'path' => $matches[0]['path'],
            'artifact' => $matches[0]['artifact'],
            'message' => null,
        ];
    }

    public function examplePath(string $filename): string
    {
        return $this->artifactRoot.DIRECTORY_SEPARATOR.'examples'.DIRECTORY_SEPARATOR.$filename;
    }

    protected function validatePayload(array $payload, ?string $expectedType = null, ?string $expectedTicker = null): void
    {
        foreach (['schema_version', 'artifact_type', 'ticker', 'generated_at', 'quality'] as $requiredKey) {
            if (! array_key_exists($requiredKey, $payload)) {
                throw new InvalidArgumentException("Research artifact missing required key: {$requiredKey}");
            }
        }

        $artifactType = (string) $payload['artifact_type'];
        $schema = (string) $payload['schema_version'];
        $supportedSchema = self::SUPPORTED_SCHEMAS[$artifactType] ?? null;

        if ($supportedSchema === null) {
            throw new InvalidArgumentException("Unsupported research artifact type: {$artifactType}");
        }

        if ($schema !== $supportedSchema) {
            throw new InvalidArgumentException("Unsupported schema for {$artifactType}: {$schema}; expected {$supportedSchema}");
        }

        if ($expectedType !== null && $artifactType !== $expectedType) {
            throw new InvalidArgumentException("Unexpected artifact type: {$artifactType}; expected {$expectedType}");
        }

        if ($expectedTicker !== null && strtoupper((string) $payload['ticker']) !== strtoupper($expectedTicker)) {
            throw new InvalidArgumentException("Unexpected artifact ticker: {$payload['ticker']}; expected {$expectedTicker}");
        }

        if (Carbon::parse($payload['generated_at']) === null) {
            throw new InvalidArgumentException('Research artifact generated_at cannot be parsed.');
        }

        if (! is_array($payload['quality'])) {
            throw new InvalidArgumentException('Research artifact quality must be an object.');
        }
    }

    protected function generatedTimestamp(array $payload): int
    {
        try {
            return Carbon::parse((string) ($payload['generated_at'] ?? '1970-01-01'))->getTimestamp();
        } catch (\Throwable) {
            return 0;
        }
    }

    protected function unavailable(string $artifactType, string $ticker, string $message): array
    {
        return [
            'available' => false,
            'artifact_type' => $artifactType,
            'ticker' => $ticker,
            'path' => null,
            'artifact' => null,
            'message' => $message,
        ];
    }
}
