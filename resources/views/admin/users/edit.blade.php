<x-app-layout>
    <div class="glass-card p-6 max-w-2xl">
        <h1 class="text-2xl font-bold mb-4">Edit User</h1>

        <form action="{{ route('admin.users.update', $user) }}" method="POST" class="space-y-4">
            @csrf
            @method('PATCH')

            <div>
                <label class="block text-sm text-slate-300">Nama</label>
                <input type="text" name="name" value="{{ old('name', $user->name) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                @error('name') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
            </div>

            <div>
                <label class="block text-sm text-slate-300">Email</label>
                <input type="email" name="email" value="{{ old('email', $user->email) }}" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                @error('email') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
            </div>

            <div>
                <label class="block text-sm text-slate-300">Role</label>
                <select name="role" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2" required>
                    <option value="user" @selected(old('role', $user->role) === 'user')>user</option>
                    <option value="admin" @selected(old('role', $user->role) === 'admin')>admin</option>
                </select>
                @error('role') <p class="text-xs text-rose-400 mt-1">{{ $message }}</p> @enderror
            </div>

            <div class="flex gap-3">
                <a href="{{ route('admin.users.index') }}" class="px-4 py-2 rounded-lg border border-slate-700 text-slate-200">Batal</a>
                <button class="px-4 py-2 rounded-lg bg-sky-500 text-slate-900 font-semibold">Simpan</button>
            </div>
        </form>
    </div>
</x-app-layout>
