package vmcmd

import (
	"encoding/json"
	"fmt"

	"dbm-services/bigdata/db-tools/dbactuator/internal/subcmd"
	"dbm-services/bigdata/db-tools/dbactuator/pkg/components/victoriametrics"
	"dbm-services/bigdata/db-tools/dbactuator/pkg/rollback"
	"dbm-services/bigdata/db-tools/dbactuator/pkg/util"
	"dbm-services/common/go-pubpkg/logger"

	"github.com/spf13/cobra"
)

// InstallVMStorageAct 结构体包含了基本选项和VictoriaMetrics服务的安装组件。
type InstallVMStorageAct struct {
	*subcmd.BaseOptions
	Service victoriametrics.InstallVMComp
}

// InstallVMStorageCommand 函数返回一个处理"install_vmstorage"命令的*cobra.Command。
// "install_vmstorage"命令用于安装VMStorage实例。
func InstallVMStorageCommand() *cobra.Command {
	// 创建一个InstallVMStorageAct对象，包含了基本选项。
	act := InstallVMStorageAct{
		BaseOptions: subcmd.GBaseOptions,
	}
	// 创建一个新的cobra.Command对象，设置其使用方法，简短描述，示例，以及运行时的函数。
	cmd := &cobra.Command{
		Use:     "install_vmstorage",
		Short:   "部署vmstorage实例",
		Example: fmt.Sprintf(`dbactuator vm install_vmstorage %s`, subcmd.CmdBaseExapmleStr),
		Run: func(cmd *cobra.Command, args []string) {
			// 验证参数，初始化，运行命令或回滚。
			util.CheckErr(act.Validate())
			if act.RollBack {
				util.CheckErr(act.Rollback())
				return
			}
			util.CheckErr(act.Init())
			util.CheckErr(act.Run())
		},
	}
	// 返回处理"install_vmstorage"命令的*cobra.Command。
	return cmd
}

// Validate 方法用于验证InstallVMStorageAct的基本选项。
func (d *InstallVMStorageAct) Validate() (err error) {
	return d.BaseOptions.Validate()
}

// Init 方法用于初始化InstallVMStorageAct。
// 它首先记录初始化的信息，然后反序列化服务参数。
// 如果反序列化失败，它将记录错误并返回。
// 最后，它将通用运行时参数设置为服务的通用参数，并初始化默认参数。
func (d *InstallVMStorageAct) Init() (err error) {
	logger.Info("InstallVMStorageAct Init")
	if err = d.Deserialize(&d.Service.Params); err != nil {
		logger.Error("DeserializeAndValidate failed, %v", err)
		return err
	}
	d.Service.GeneralParam = subcmd.GeneralRuntimeParam
	return d.Service.InitDefaultParam()
}

// Rollback 方法用于回滚InstallVMStorageAct。
// 它首先反序列化并验证回滚对象，如果失败，它将记录错误并返回。
// 然后，它尝试回滚，如果失败，它将记录错误。
func (d *InstallVMStorageAct) Rollback() (err error) {
	var r rollback.RollBackObjects
	if err = d.DeserializeAndValidate(&r); err != nil {
		logger.Error("DeserializeAndValidate failed, %v", err)
		return err
	}
	err = r.RollBack()
	if err != nil {
		logger.Error("roll back failed %s", err.Error())
	}
	return
}

// Run 方法用于运行InstallVMStorageAct。
// 它首先定义了一个步骤，该步骤的函数是安装VMStorage。
// 然后，它运行这个步骤，如果失败，它将尝试回滚，并记录回滚的上下文。
// 如果回滚失败，它将记录错误并打印无法回滚的消息。
// 最后，如果一切顺利，它将记录成功的消息。
func (d *InstallVMStorageAct) Run() (err error) {
	steps := subcmd.Steps{
		{
			FunName: "部署vmstorage",
			Func:    d.Service.InstallVMStorage,
		},
	}

	if err := steps.Run(); err != nil {
		rollbackCtxb, rerr := json.Marshal(d.Service.RollBackContext)
		if rerr != nil {
			logger.Error("json Marshal %s", err.Error())
			fmt.Printf("<ctx>Can't RollBack<ctx>\n")
		}
		fmt.Printf("<ctx>%s<ctx>\n", string(rollbackCtxb))
		return err
	}

	logger.Info("install_vmstorage successfully")
	return nil
}
