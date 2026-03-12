return {
  {
    "akinsho/toggleterm.nvim",
    version = "*",
    opts = function(_, opts)
      opts = opts or {}
      local Terminal = require("toggleterm.terminal").Terminal
      opts.size = function(term)
        if term.direction == "vertical" then
          return math.floor(vim.o.columns * 0.32)
        end
        return math.floor(vim.o.lines * 0.25)
      end
      local codex
      local shell

      local function ensure_server()
        if vim.v.servername ~= nil and vim.v.servername ~= "" then
          return vim.v.servername
        end

        local server = string.format("%s/geek-env-%d.sock", vim.fn.stdpath("run"), vim.fn.getpid())
        pcall(vim.fn.delete, server)
        return vim.fn.serverstart(server)
      end

      local function remote_editor_cmd()
        local server = ensure_server()
        return string.format("nvim --server %s --remote-tab-wait", vim.fn.shellescape(server))
      end

      local function terminal_filetype(filetype)
        return function(term)
          if term.bufnr and vim.api.nvim_buf_is_valid(term.bufnr) then
            vim.bo[term.bufnr].filetype = filetype
          end
        end
      end

      local function codex_cmd()
        local editor = remote_editor_cmd()
        return string.format(
          "env EDITOR=%s VISUAL=%s codex",
          vim.fn.shellescape(editor),
          vim.fn.shellescape(editor)
        )
      end

      local function get_codex()
        if codex then
          return codex
        end

        codex = Terminal:new({
          cmd = codex_cmd(),
          direction = "vertical",
          hidden = true,
          close_on_exit = false,
          on_open = terminal_filetype("codex_panel"),
        })
        return codex
      end

      local function get_shell()
        if shell then
          return shell
        end

        shell = Terminal:new({
          cmd = vim.o.shell,
          direction = "horizontal",
          hidden = true,
          close_on_exit = false,
          on_open = terminal_filetype("shell_panel"),
        })
        return shell
      end

      vim.api.nvim_create_user_command("CodexToggle", function()
        get_codex():toggle()
      end, { desc = "Toggle Codex panel" })

      vim.api.nvim_create_user_command("CodexNew", function()
        Terminal:new({
          cmd = codex_cmd(),
          direction = "vertical",
          hidden = true,
          close_on_exit = false,
          on_open = terminal_filetype("codex_panel"),
        }):toggle()
      end, { desc = "Open a new Codex panel" })

      vim.api.nvim_create_user_command("TerminalToggle", function()
        get_shell():toggle()
      end, { desc = "Toggle shell panel" })

      vim.api.nvim_create_user_command("TerminalNew", function()
        Terminal:new({
          cmd = vim.o.shell,
          direction = "horizontal",
          hidden = true,
          close_on_exit = false,
          on_open = terminal_filetype("shell_panel"),
        }):toggle()
      end, { desc = "Open a new shell panel" })

      vim.api.nvim_create_autocmd("VimEnter", {
        group = vim.api.nvim_create_augroup("geek_env_layout", { clear = true }),
        once = true,
        callback = function()
          vim.schedule(function()
            ensure_server()
            local ok, edgy = pcall(require, "edgy")
            if ok then
              edgy.open()
            end
          end)
        end,
      })

      return opts
    end,
  },
}
