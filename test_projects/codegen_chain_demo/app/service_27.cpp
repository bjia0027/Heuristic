#include "service_27.h"

Service27::Service27() {}

void Service27::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service27::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
