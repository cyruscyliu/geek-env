return {
  {
    "Mofiqul/vscode.nvim",
    name = "vscode",
    priority = 1000,
    opts = {
      style = "dark",
      transparent = false,
      italic_comments = true,
      disable_nvimtree_bg = true,
    },
    config = function(_, opts)
      require("vscode").setup(opts)
      vim.cmd.colorscheme("vscode")
      vim.o.winbar = "%{%v:lua.require'config.winbar'.get()%}"
    end,
  },
  {
    "akinsho/bufferline.nvim",
    version = "*",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
      options = {
        mode = "buffers",
        diagnostics = "nvim_lsp",
        always_show_bufferline = true,
        separator_style = "thin",
        show_buffer_close_icons = false,
        show_close_icon = false,
        offsets = {
          {
            filetype = "neo-tree",
            text = "Explorer",
            highlight = "Directory",
            text_align = "left",
          },
        },
      },
    },
  },
  {
    "nvim-lualine/lualine.nvim",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
      options = {
        theme = "vscode",
        globalstatus = true,
      },
    },
  },
  {
    "folke/trouble.nvim",
    cmd = "Trouble",
    keys = {
      {
        "<leader>xx",
        "<cmd>Trouble diagnostics toggle focus=false win.position=bottom<cr>",
        desc = "Diagnostics panel",
      },
      {
        "<leader>xX",
        "<cmd>Trouble diagnostics toggle focus=false filter.buf=0 win.position=bottom<cr>",
        desc = "Buffer diagnostics panel",
      },
      {
        "<leader>cs",
        "<cmd>Trouble symbols toggle focus=false win.position=right<cr>",
        desc = "Symbols panel",
      },
      {
        "<leader>cl",
        "<cmd>Trouble lsp toggle focus=false win.position=right<cr>",
        desc = "LSP list panel",
      },
    },
    opts = {
      focus = false,
      auto_preview = false,
      win = {
        type = "split",
        position = "bottom",
      },
    },
  },
  {
    "folke/edgy.nvim",
    lazy = false,
    init = function()
      vim.opt.laststatus = 3
      vim.opt.splitkeep = "screen"
    end,
    opts = {
      left = {
        {
          ft = "neo-tree",
          title = "Explorer",
          size = {
            width = 32,
          },
          pinned = true,
          open = "Neotree show filesystem left",
        },
      },
      bottom = {
        {
          ft = "shell_panel",
          title = "Terminal",
          size = {
            height = 0.25,
          },
          pinned = true,
          open = "TerminalToggle",
        },
        {
          ft = "Trouble",
          title = "Problems",
          size = {
            height = 0.25,
          },
          collapsed = true,
        },
      },
      right = {
        {
          ft = "codex_panel",
          title = "Codex",
          size = {
            width = 0.32,
          },
          pinned = true,
          open = "CodexToggle",
        },
        {
          ft = "Outline",
          title = "Symbols",
          size = {
            width = 0.25,
          },
          collapsed = true,
        },
      },
    },
  },
}
