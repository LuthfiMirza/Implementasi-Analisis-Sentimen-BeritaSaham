<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Stock;
use Illuminate\Http\Request;

class StockController extends Controller
{
    /**
     * Display a listing of the resource.
     */
    public function index()
    {
        $stocks = Stock::orderBy('code')->paginate(20);

        return view('admin.stocks.index', compact('stocks'));
    }

    /**
     * Show the form for creating a new resource.
     */
    public function create()
    {
        return view('admin.stocks.create');
    }

    /**
     * Store a newly created resource in storage.
     */
    public function store(Request $request)
    {
        $validated = $this->validateData($request);
        Stock::create($validated);

        return redirect()->route('admin.stocks.index')->with('status', 'Saham berhasil dibuat.');
    }

    /**
     * Display the specified resource.
     */
    public function show(Stock $stock)
    {
        //
    }

    /**
     * Show the form for editing the specified resource.
     */
    public function edit(Stock $stock)
    {
        return view('admin.stocks.edit', compact('stock'));
    }

    /**
     * Update the specified resource in storage.
     */
    public function update(Request $request, Stock $stock)
    {
        $validated = $this->validateData($request, $stock->id);
        $stock->update($validated);

        return redirect()->route('admin.stocks.index')->with('status', 'Data saham diperbarui.');
    }

    /**
     * Remove the specified resource from storage.
     */
    public function destroy(Stock $stock)
    {
        $stock->delete();

        return redirect()->route('admin.stocks.index')->with('status', 'Saham dihapus.');
    }

    protected function validateData(Request $request, ?int $ignoreId = null): array
    {
        $data = $request->validate([
            'code' => ['required', 'string', 'max:10', 'unique:stocks,code'.($ignoreId ? ','.$ignoreId : '')],
            'company_name' => ['required', 'string'],
            'sector' => ['nullable', 'string'],
            'description' => ['nullable', 'string'],
            'exchange' => ['required', 'string'],
            'tradingview_symbol' => ['nullable', 'string'],
            'yahoo_symbol' => ['nullable', 'string'],
            'is_active' => ['boolean'],
        ]);

        $data['is_active'] = $request->boolean('is_active', true);

        return $data;
    }
}
