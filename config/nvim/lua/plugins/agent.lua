return {
  {
    "akinsho/toggleterm.nvim",
    opts = function(_, opts)
      local Terminal = require("toggleterm.terminal").Terminal
      local codex = Terminal:new({
        cmd = "codex",
        direction = "float",
        hidden = true,
        close_on_exit = false,
        float_opts = {
          border = "curved",
        },
      })

      vim.api.nvim_create_user_command("CodexToggle", function()
        codex:toggle()
      end, { desc = "Toggle Codex terminal" })

      vim.api.nvim_create_user_command("CodexNew", function()
        Terminal:new({
          cmd = "codex",
          direction = "horizontal",
          close_on_exit = false,
          hidden = true,
        }):toggle()
      end, { desc = "Open a new Codex terminal" })

      return opts
    end,
  },
}
