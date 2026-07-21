<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class RefreshPriceHistoryCommandTest extends TestCase
{
    public function test_successful_run_reports_rebuilt_tickers(): void
    {
        Process::fake([
            '*' => Process::result(output: json_encode([
                'series' => [
                    ['name' => 'BBCA', 'symbol' => 'BBCA.JK', 'status' => 'rebuilt', 'rows' => 6200, 'date_start' => '2001-01-02', 'date_end' => '2026-07-17', 'issues' => [], 'output_path' => 'data/stocks/BBCA.csv'],
                ],
            ])),
        ]);

        $this->artisan('prediction:refresh-price-history')
            ->expectsOutputToContain('Rebuilt BBCA')
            ->assertExitCode(0);
    }

    public function test_ticker_option_filters_series_argument(): void
    {
        Process::fake([
            '*' => Process::result(output: json_encode([
                'series' => [
                    ['name' => 'BBCA', 'symbol' => 'BBCA.JK', 'status' => 'rebuilt', 'rows' => 6200, 'date_start' => '2001-01-02', 'date_end' => '2026-07-17', 'issues' => [], 'output_path' => 'data/stocks/BBCA.csv'],
                ],
            ])),
        ]);

        $this->artisan('prediction:refresh-price-history', ['--ticker' => ['BBCA']])
            ->assertExitCode(0);

        Process::assertRan(function ($process) {
            $command = $process->command;
            $hasBBCA = in_array('BBCA=BBCA.JK', $command, true);
            $hasBBRI = in_array('BBRI=BBRI.JK', $command, true);

            return $hasBBCA && ! $hasBBRI;
        });
    }

    public function test_ihsg_always_refreshes_even_when_ticker_option_narrows_stocks(): void
    {
        Process::fake([
            '*' => Process::result(output: json_encode([
                'series' => [
                    ['name' => 'BBCA', 'symbol' => 'BBCA.JK', 'status' => 'rebuilt', 'rows' => 6200, 'date_start' => '2001-01-02', 'date_end' => '2026-07-17', 'issues' => [], 'output_path' => 'data/stocks/BBCA.csv'],
                ],
            ])),
        ]);

        $this->artisan('prediction:refresh-price-history', ['--ticker' => ['BBCA']])
            ->assertExitCode(0);

        Process::assertRan(fn ($process) => in_array('IHSG=^JKSE', $process->command, true)
            && in_array('data', $process->command, true));
    }

    public function test_partial_invalid_tickers_do_not_fail_command(): void
    {
        Process::fake([
            '*' => Process::result(
                output: json_encode([
                    'series' => [
                        ['name' => 'BBCA', 'symbol' => 'BBCA.JK', 'status' => 'rebuilt', 'rows' => 6200, 'date_start' => '2001-01-02', 'date_end' => '2026-07-17', 'issues' => [], 'output_path' => 'data/stocks/BBCA.csv'],
                        ['name' => 'GOTO', 'symbol' => 'GOTO.JK', 'status' => 'invalid', 'rows' => 0, 'date_start' => null, 'date_end' => null, 'issues' => ['empty_history'], 'output_path' => 'data/stocks/GOTO.csv'],
                    ],
                ]),
                exitCode: 1,
            ),
        ]);

        $this->artisan('prediction:refresh-price-history')
            ->expectsOutputToContain('Rebuilt BBCA')
            ->expectsOutputToContain('Skip GOTO')
            ->assertExitCode(0);
    }

    public function test_all_tickers_invalid_fails_command(): void
    {
        Process::fake([
            '*' => Process::result(
                output: json_encode([
                    'series' => [
                        ['name' => 'BBCA', 'symbol' => 'BBCA.JK', 'status' => 'invalid', 'rows' => 0, 'date_start' => null, 'date_end' => null, 'issues' => ['empty_history'], 'output_path' => 'data/stocks/BBCA.csv'],
                    ],
                ]),
                exitCode: 1,
            ),
        ]);

        $this->artisan('prediction:refresh-price-history')
            ->assertExitCode(1);
    }

    public function test_non_json_output_fails_gracefully(): void
    {
        Process::fake([
            '*' => Process::result(output: 'Traceback: ModuleNotFoundError', exitCode: 1),
        ]);

        $this->artisan('prediction:refresh-price-history')
            ->assertExitCode(1);
    }
}
