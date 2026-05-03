<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Illuminate\View\View;

class UserController extends Controller
{
    /**
     * Display paginated application users for administrator review.
     */
    public function index(): View
    {
        $users = User::query()
            ->orderBy('name')
            ->paginate(15);

        return view('admin.users.index', compact('users'));
    }

    /**
     * Show the administrator edit form for one user.
     */
    public function edit(User $user): View
    {
        return view('admin.users.edit', compact('user'));
    }

    /**
     * Persist administrator changes to a user's identity and role.
     */
    public function update(Request $request, User $user): RedirectResponse
    {
        $validated = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'max:255', Rule::unique('users', 'email')->ignore($user->id)],
            'role' => ['required', Rule::in(['admin', 'user'])],
        ]);

        $user->update($validated);

        return redirect()->route('admin.users.index')->with('status', 'User berhasil diperbarui.');
    }

    /**
     * Delete a user while preventing administrators from deleting themselves.
     */
    public function destroy(User $user): RedirectResponse
    {
        if ($user->id === auth()->id()) {
            abort(403);
        }

        $user->delete();

        return redirect()->route('admin.users.index')->with('status', 'User berhasil dihapus.');
    }
}
