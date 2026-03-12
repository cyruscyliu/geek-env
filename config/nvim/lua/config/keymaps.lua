local map = vim.keymap.set

map("n", "<leader>w", "<cmd>write<cr>", { desc = "Write file" })
map("n", "<leader>q", "<cmd>quit<cr>", { desc = "Quit window" })
map("n", "<Esc>", "<cmd>nohlsearch<cr>", { desc = "Clear search highlight" })
map("n", "<leader>aa", "<cmd>CodexToggle<cr>", { desc = "Toggle Codex panel" })
map("n", "<leader>an", "<cmd>CodexNew<cr>", { desc = "New Codex panel" })
map("n", "<leader>at", "<cmd>TerminalToggle<cr>", { desc = "Toggle shell panel" })
map("n", "<leader>aT", "<cmd>TerminalNew<cr>", { desc = "New shell panel" })

map("n", "<C-h>", "<C-w><C-h>", { desc = "Move to left split" })
map("n", "<C-l>", "<C-w><C-l>", { desc = "Move to right split" })
map("n", "<C-j>", "<C-w><C-j>", { desc = "Move to lower split" })
map("n", "<C-k>", "<C-w><C-k>", { desc = "Move to upper split" })
