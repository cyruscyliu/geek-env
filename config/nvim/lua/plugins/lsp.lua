return {
  {
    "williamboman/mason.nvim",
    opts = {},
  },
  {
    "williamboman/mason-lspconfig.nvim",
    dependencies = {
      "williamboman/mason.nvim",
      "neovim/nvim-lspconfig",
    },
    opts = {
      ensure_installed = {
        "bashls",
        "jsonls",
        "lua_ls",
        "marksman",
        "pyright",
      },
    },
  },
  {
    "neovim/nvim-lspconfig",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/nvim-cmp",
      "L3MON4D3/LuaSnip",
      "saadparwaiz1/cmp_luasnip",
      "rafamadriz/friendly-snippets",
      "SmiteshP/nvim-navic",
    },
    config = function()
      local cmp = require("cmp")
      local luasnip = require("luasnip")
      local navic = require("nvim-navic")
      local capabilities = require("cmp_nvim_lsp").default_capabilities()

      require("luasnip.loaders.from_vscode").lazy_load()
      require("mason").setup()
      require("mason-lspconfig").setup()
      navic.setup({
        highlight = true,
        separator = " > ",
        depth_limit = 5,
      })

      cmp.setup({
        snippet = {
          expand = function(args)
            luasnip.lsp_expand(args.body)
          end,
        },
        mapping = cmp.mapping.preset.insert({
          ["<C-Space>"] = cmp.mapping.complete(),
          ["<CR>"] = cmp.mapping.confirm({ select = true }),
          ["<Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.select_next_item()
            elseif luasnip.expand_or_locally_jumpable() then
              luasnip.expand_or_jump()
            else
              fallback()
            end
          end, { "i", "s" }),
          ["<S-Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.select_prev_item()
            elseif luasnip.locally_jumpable(-1) then
              luasnip.jump(-1)
            else
              fallback()
            end
          end, { "i", "s" }),
        }),
        sources = {
          { name = "nvim_lsp" },
          { name = "luasnip" },
        },
      })

      local on_attach = function(client, bufnr)
        local map = function(keys, func, desc)
          vim.keymap.set("n", keys, func, { buffer = bufnr, desc = desc })
        end

        if client.server_capabilities.documentSymbolProvider then
          navic.attach(client, bufnr)
        end

        map("gd", vim.lsp.buf.definition, "Go to definition")
        map("gr", vim.lsp.buf.references, "Go to references")
        map("K", vim.lsp.buf.hover, "Hover docs")
        map("<leader>rn", vim.lsp.buf.rename, "Rename symbol")
        map("<leader>ca", vim.lsp.buf.code_action, "Code action")
      end

      local servers = {
        bashls = {},
        jsonls = {},
        lua_ls = {
          settings = {
            Lua = {
              diagnostics = { globals = { "vim" } },
              workspace = { checkThirdParty = false },
            },
          },
        },
        marksman = {},
        pyright = {},
      }

      for server, server_opts in pairs(servers) do
        server_opts.capabilities = capabilities
        server_opts.on_attach = on_attach

        if vim.lsp.config and vim.lsp.enable then
          vim.lsp.config(server, server_opts)
          vim.lsp.enable(server)
        else
          require("lspconfig")[server].setup(server_opts)
        end
      end
    end,
  },
}
