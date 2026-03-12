vim.api.nvim_create_autocmd("VimEnter", {
  group = vim.api.nvim_create_augroup("geek_env_startup", { clear = true }),
  callback = function()
    local arg = vim.fn.argv(0)

    if vim.fn.argc() ~= 1 or vim.fn.isdirectory(arg) == 0 then
      return
    end

    vim.cmd.cd(arg)
  end,
})
