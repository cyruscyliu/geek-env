return {
  {
    "ahmedkhalf/project.nvim",
    main = "project_nvim",
    lazy = false,
    opts = {
      manual_mode = false,
      detection_methods = { "pattern", "lsp" },
      patterns = {
        ".git",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "Makefile",
      },
      silent_chdir = true,
      scope_chdir = "global",
    },
  },
  {
    "nvim-neo-tree/neo-tree.nvim",
    branch = "v3.x",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "MunifTanjim/nui.nvim",
      "nvim-tree/nvim-web-devicons",
    },
    cmd = "Neotree",
    keys = {
      { "<leader>e", "<cmd>Neotree toggle filesystem left<cr>", desc = "Toggle explorer" },
    },
    opts = {
      close_if_last_window = false,
      popup_border_style = "rounded",
      enable_git_status = true,
      enable_diagnostics = true,
      open_files_do_not_replace_types = {
        "terminal",
        "Trouble",
        "qf",
        "edgy",
      },
      filesystem = {
        follow_current_file = {
          enabled = true,
          leave_dirs_open = false,
        },
        hijack_netrw_behavior = "open_default",
        filtered_items = {
          visible = true,
          hide_dotfiles = false,
          hide_gitignored = false,
        },
        window = {
          position = "left",
          width = 32,
        },
      },
      default_component_configs = {
        indent = {
          with_expanders = true,
          expander_collapsed = ">",
          expander_expanded = "v",
        },
      },
      window = {
        mappings = {
          ["l"] = "open",
          ["h"] = "close_node",
        },
      },
    },
  },
  {
    "nvim-telescope/telescope.nvim",
    branch = "0.1.x",
    dependencies = { "nvim-lua/plenary.nvim" },
    keys = {
      { "<leader>ff", "<cmd>Telescope find_files<cr>", desc = "Find files" },
      { "<leader>fg", "<cmd>Telescope live_grep<cr>", desc = "Live grep" },
      { "<leader>fb", "<cmd>Telescope buffers<cr>", desc = "Buffers" },
      { "<leader>fh", "<cmd>Telescope help_tags<cr>", desc = "Help tags" },
    },
  },
  {
    "nvim-treesitter/nvim-treesitter",
    lazy = false,
    build = ":TSUpdate",
    opts = {
      ensure_installed = {
        "bash",
        "css",
        "html",
        "javascript",
        "json",
        "lua",
        "markdown",
        "python",
        "tsx",
        "typescript",
        "vim",
        "yaml",
      },
      auto_install = true,
      highlight = { enable = true },
      indent = { enable = true },
    },
    config = function(_, opts)
      local ok_configs, configs = pcall(require, "nvim-treesitter.configs")
      if ok_configs then
        configs.setup(opts)
        return
      end

      local ok_ts, ts = pcall(require, "nvim-treesitter")
      if not ok_ts then
        vim.notify("nvim-treesitter is not available", vim.log.levels.ERROR)
        return
      end

      if ts.setup then
        ts.setup({})
      end

      local languages = opts.ensure_installed or {}
      if #languages > 0 and ts.install then
        ts.install(languages)
      end

      if opts.highlight and opts.highlight.enable then
        vim.api.nvim_create_autocmd("FileType", {
          group = vim.api.nvim_create_augroup("geek-env-treesitter-highlight", { clear = true }),
          callback = function(event)
            pcall(vim.treesitter.start, event.buf)
          end,
        })
      end

      if opts.indent and opts.indent.enable and ts.indentexpr then
        vim.api.nvim_create_autocmd("FileType", {
          group = vim.api.nvim_create_augroup("geek-env-treesitter-indent", { clear = true }),
          callback = function(event)
            vim.bo[event.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
          end,
        })
      end
    end,
  },
  {
    "folke/which-key.nvim",
    event = "VeryLazy",
    opts = {},
  },
}
