<?php

namespace App\Services\News;

use App\Models\Stock;
use Illuminate\Support\Str;

class StockKeywordMapper
{
    /**
     * Override manual per kode emiten jika butuh kata kunci khusus.
     * Tambahkan sesuai kebutuhan.
     */
    protected array $overrides = [
        'BBCA' => ['BBCA', 'BCA', 'Bank Central Asia', 'BCA Digital'],
        'BBRI' => ['BBRI', 'BRI', 'Bank Rakyat Indonesia'],
        'BMRI' => ['BMRI', 'Bank Mandiri'],
        'TLKM' => ['TLKM', 'Telkom', 'Telkom Indonesia'],
        'ASII' => ['ASII', 'Astra', 'Astra International'],
        'GOTO' => ['GOTO', 'GoTo Group', 'GoTo Gojek Tokopedia', 'Gojek', 'Tokopedia'],
        'UNVR' => ['UNVR', 'Unilever Indonesia'],
        'INDF' => ['INDF', 'Indofood', 'Indofood Sukses Makmur'],
        'ICBP' => ['ICBP', 'Indofood CBP'],
        'ADRO' => ['ADRO', 'Adaro', 'Adaro Energy'],
    ];

    /**
     * Kata kunci pengecualian per saham untuk menghindari konteks salah.
     */
    protected array $exclusions = [
        'GOTO' => ['goto islands', 'goto island', 'camellia', 'nagasaki', 'archipelago', 'tsubaki'],
    ];

    public function keywords(Stock $stock): array
    {
        $code = $stock->code;
        $name = $stock->company_name ?? $stock->code;

        $cleanName = trim(Str::of($name)->replace(['Tbk', 'tbk.', 'TBK', '.', ','], ' ')->squish());
        $parts = collect(explode(' ', $cleanName))
            ->filter()
            ->values();

        // Nama pendek: 2-3 kata pertama
        $short = $parts->take(3)->implode(' ');

        $aliases = collect([$code, $cleanName, $short])
            ->filter()
            ->unique()
            ->values()
            ->all();

        if (array_key_exists($code, $this->overrides)) {
            $aliases = array_values(array_unique(array_merge($this->overrides[$code], $aliases)));
        }

        return $aliases;
    }

    public function exclusionKeywords(Stock $stock): array
    {
        return $this->exclusions[$stock->code] ?? [];
    }

    public function queryString(Stock $stock): string
    {
        $keywords = $this->keywords($stock);
        return collect($keywords)->map(fn ($k) => "\"{$k}\"")->implode(' OR ');
    }
}
