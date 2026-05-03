<x-app-layout>
    <div class="glass-card p-6 space-y-4">
        <div>
            <p class="text-xs text-slate-400 uppercase">Admin</p>
            <h1 class="text-2xl font-bold">Kelola User</h1>
        </div>

        @if (session('status'))
            <div class="text-green-400 text-sm">{{ session('status') }}</div>
        @endif

        <div class="overflow-hidden rounded-xl border border-slate-800">
            <table class="min-w-full divide-y divide-slate-800 text-sm">
                <thead class="bg-slate-900/70 text-slate-400 uppercase">
                    <tr>
                        <th class="px-4 py-3 text-left">Nama</th>
                        <th class="px-4 py-3 text-left">Email</th>
                        <th class="px-4 py-3 text-left">Role</th>
                        <th class="px-4 py-3 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach($users as $user)
                        <tr class="hover:bg-slate-900/60">
                            <td class="px-4 py-3 font-semibold">{{ $user->name }}</td>
                            <td class="px-4 py-3 text-slate-300">{{ $user->email }}</td>
                            <td class="px-4 py-3">
                                <span class="text-xs px-2 py-1 rounded-full {{ $user->role === 'admin' ? 'bg-sky-500/20 text-sky-300' : 'bg-slate-800 text-slate-300' }}">
                                    {{ $user->role }}
                                </span>
                            </td>
                            <td class="px-4 py-3 text-right space-x-2">
                                <a href="{{ route('admin.users.edit', $user) }}" class="text-sky-400 text-xs">Edit</a>
                                @if($user->id !== auth()->id())
                                    <form action="{{ route('admin.users.destroy', $user) }}" method="POST" class="inline">
                                        @csrf
                                        @method('DELETE')
                                        <button class="text-rose-400 text-xs" onclick="return confirm('Hapus user ini?')">Hapus</button>
                                    </form>
                                @endif
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>

        {{ $users->links() }}
    </div>
</x-app-layout>
