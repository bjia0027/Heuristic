#pragma once
#include <functional>
#include <vector>

class Service16 {
public:
    Service16();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
